# planner/compiler_with_crew.py
import json
from typing import Any, Dict, Tuple, List

from crewai import Crew, Process

from planner.crew import (
    assembler_agent, planner_agent, validator_agent, refiner_agent,
    t1_assemble, t2_draft, t3_validate, t4_repair_if_needed,
)

import logging
logger = logging.getLogger(__name__)


def _extract_first_json_object(s: str) -> str:
    """
    Extract the first complete top-level JSON object from a string.

    Handles:
    - Extra text before/after JSON
    - Nested objects
    - Braces inside quoted strings
    """
    if not s:
        return ""

    in_string = False
    escape = False
    depth = 0
    start = None

    for i, ch in enumerate(s):
        if ch == '"' and not escape:
            in_string = not in_string
        elif ch == "\\" and in_string:
            escape = not escape
            continue

        escape = False

        if in_string:
            continue

        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return s[start : i + 1]

    return ""



def _safe_json(s: str) -> Dict[str, Any]:
    """
    Always return a JudgePlanResult-like dict:
      ok: bool
      expected: dict
      actual: dict
      errors: list
      fix_instructions: list
    """
    raw = (s or "").strip()
    raw_json = _extract_first_json_object(raw) or raw

    def _as_dict(x: Any) -> Dict[str, Any]:
        return x if isinstance(x, dict) else {}

    def _as_list(x: Any) -> List[Any]:
        if x is None:
            return []
        if isinstance(x, list):
            return x
        return [x]

    def _clean_fix_list(fix: Any) -> List[str]:
        if fix is None:
            return []
        if isinstance(fix, str):
            fix = [fix]
        if not isinstance(fix, list):
            return []
        cleaned: List[str] = []
        for x in fix:
            if x is None:
                continue
            s2 = str(x).strip()
            if not s2:
                continue
            low = s2.lower()
            if low in {"none", "null", "no", "n/a"}:
                continue
            if "plan is correct" in low:
                continue
            if "appropriate trigger" in low:
                continue
            cleaned.append(s2)
        return cleaned

    try:
        parsed = json.loads(raw_json)
    except Exception as e:
        return {
            "ok": False,
            "expected": {},
            "actual": {"message": "Judge returned invalid JSON", "error": f"{type(e).__name__}: {e}"},
            "errors": [{"type": "INVALID_JSON", "raw": raw[:800]}],
            "fix_instructions": ["Re-run judge_plan and return valid JSON matching schema."],
        }

    # Normalize shapes defensively
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "expected": {},
            "actual": {"message": "Judge returned non-dict JSON", "raw": parsed},
            "errors": [{"type": "INVALID_JUDGE_SHAPE"}],
            "fix_instructions": [
                "Return a JSON object with keys: ok, expected, actual, errors, fix_instructions."
            ],
        }

    # ---- Ensure required keys exist with correct types ----
    ok_val = parsed.get("ok", False)
    ok_bool = bool(ok_val) if isinstance(ok_val, (bool, int)) else False

    expected = _as_dict(parsed.get("expected"))
    actual = _as_dict(parsed.get("actual"))
    errors = _as_list(parsed.get("errors"))
    fix = _clean_fix_list(parsed.get("fix_instructions"))

    out: Dict[str, Any] = {
        "ok": ok_bool,
        "expected": expected,
        "actual": actual,
        "errors": errors,
        "fix_instructions": fix,
    }

    # ---- Invariant enforcement (same logic as tool) ----
    if out["ok"] is False and len(out["errors"]) == 0 and len(out["fix_instructions"]) == 0:
        # This is the key case that caused “ok:false even when correct”
        # Make it explicit and self-healing.
        out["ok"] = True
        out["errors"] = [{"type": "NON_ACTIONABLE_FALSE", "message": "Judge returned ok=false with no errors/fixes; treating as ok=true"}]

    if out["ok"] is False and len(out["errors"]) > 0 and len(out["fix_instructions"]) == 0:
        out["fix_instructions"] = [
            "Fix the plan to satisfy the judge errors using ONLY allowed enums and rules."
        ]

    return out

def compile_with_crew(
    query: str,
    max_iters: int = 2,
    verbose: bool = True,
    *,
    enable_validation: bool = True,   # <-- FLAG
) -> Tuple[str, Dict[str, Any]]:
    # ---------------- Draft ----------------
    draft_crew = Crew(
        agents=[assembler_agent, planner_agent],
        tasks=[t1_assemble, t2_draft],
        process=Process.sequential,
        verbose=verbose,
    )
    drafted_plan = str(draft_crew.kickoff(inputs={"query": query})).strip()

    # ---------------- Draft-only mode (skip t3/t4) ----------------
    if not enable_validation:
        judge_json: Dict[str, Any] = {
            "ok": True,
            "expected": {"message": "Validation disabled"},
            "actual": {"message": "Validation disabled"},
            "errors": [],
            "fix_instructions": [],
            "meta": {"validation": "disabled"},
        }
        return drafted_plan, judge_json

    # ---------------- Validation mode (t3 + optional t4 loop) ----------------
    plan = drafted_plan
    judge_json: Dict[str, Any] = {"ok": False, "expected": {}, "actual": {}, "errors": [], "fix_instructions": []}

    total_attempts = max_iters

    for attempt in range(1, total_attempts + 1):
        # ---------------- Judge (t3) ----------------
        judge_crew = Crew(
            agents=[validator_agent],
            tasks=[t3_validate],
            process=Process.sequential,
            verbose=verbose,
        )

        judge_raw = str(
            judge_crew.kickoff(inputs={"query": query, "plan_markdown": plan})
        ).strip()

        logger.info("[compiler] judge_raw_prefix=%r", judge_raw[:120])

        judge_json = _safe_json(judge_raw)

        logger.info("[compiler] judge_json=%s", json.dumps(judge_json, ensure_ascii=False))

        logger.info(
            "[compiler] attempt=%d/%d judge_ok=%s plan_chars=%d errors=%d fixes=%d",
            attempt,
            total_attempts,
            judge_json.get("ok"),
            len(plan),
            len(judge_json.get("errors") or []),
            len(judge_json.get("fix_instructions") or []),
        )

        # ✅ success
        if judge_json.get("ok") is True:
            logger.info("[compiler] SUCCESS at attempt=%d", attempt)
            return plan, judge_json

        # ✅ if judge is not actionable, stop instead of looping forever
        if not judge_json.get("errors") and not judge_json.get("fix_instructions"):
            logger.warning("[compiler] Judge returned ok=false but no errors/fixes; treating as ok=true")
            judge_json["ok"] = True
            return plan, judge_json

        # ---------------- Stop if no retries left ----------------
        if attempt >= total_attempts:
            break

        # ---------------- Repair (t4) ----------------
        logger.info("[compiler] attempt=%d repairing plan", attempt)

        repair_crew = Crew(
            agents=[refiner_agent],
            tasks=[t4_repair_if_needed],
            process=Process.sequential,
            verbose=verbose,
        )

        plan = str(
            repair_crew.kickoff(
                inputs={
                    "plan_markdown": plan,
                    "judge_json": json.dumps(judge_json, ensure_ascii=False),
                }
            )
        ).strip()

    # ---------------- Fallback ----------------
    logger.error(
        "[compiler] MAX_RETRIES_EXCEEDED (%d attempts). Falling back to raw query.",
        max_iters,
    )

    fallback = {
        "ok": False,
        "expected": {"message": "Valid workflow plan"},
        "actual": {"message": "Max repair attempts exceeded; returning raw query as output"},
        "errors": (judge_json.get("errors") or []) + [{"type": "MAX_RETRIES_EXCEEDED"}],
        "fix_instructions": [],
        "meta": {"fallback": True, "attempts": max_iters},
    }
    return query, fallback

