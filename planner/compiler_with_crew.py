# planner/compiler_with_crew.py
import json
from typing import Any, Dict, Tuple

from crewai import Crew, Process

from planner.crew import (
    assembler_agent, planner_agent, validator_agent, refiner_agent,
    t1_assemble, t2_draft, t3_validate, t4_repair_if_needed,
)

import logging
logger = logging.getLogger(__name__)


def _extract_first_json_object(s: str) -> str:
    """
    Crew agents sometimes wrap tool output with extra text.
    This extracts the outermost {...} block.
    """
    if not s:
        return ""
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return ""
    return s[start : end + 1]


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

    try:
        parsed = json.loads(raw_json)
    except Exception:
        return {
            "ok": False,
            "expected": {},
            "actual": {"message": "Judge returned invalid JSON"},
            "errors": [{"type": "INVALID_JSON", "raw": raw[:800]}],
            "fix_instructions": [
                "Re-run judge_plan and return valid JSON matching schema."
            ],
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

    # Ensure required keys exist with correct types
    parsed.setdefault("ok", False)
    parsed.setdefault("expected", {})
    parsed.setdefault("actual", {})
    parsed.setdefault("errors", [])
    parsed.setdefault("fix_instructions", [])

    # Coerce types if needed
    if not isinstance(parsed["expected"], dict):
        parsed["expected"] = {"value": parsed["expected"]}
    if not isinstance(parsed["actual"], dict):
        parsed["actual"] = {"value": parsed["actual"]}
    if not isinstance(parsed["errors"], list):
        parsed["errors"] = [parsed["errors"]]
    if not isinstance(parsed["fix_instructions"], list):
        parsed["fix_instructions"] = [parsed["fix_instructions"]]

    def _clean_list(xs):
        out = []
        for x in xs or []:
            if x is None:
                continue
            if isinstance(x, str):
                s = x.strip()
                if s == "" or s.lower() == "none":
                    continue
                out.append(s)
            else:
                out.append(x)
        return out

    parsed["errors"] = _clean_list(parsed.get("errors"))
    parsed["fix_instructions"] = _clean_list(parsed.get("fix_instructions"))


    return parsed


def compile_with_crew(query: str, max_iters: int = 2, verbose: bool = True) -> Tuple[str, Dict[str, Any]]:
    orig_max_iters = max_iters

    # ---------------- Draft ----------------
    draft_crew = Crew(
        agents=[assembler_agent, planner_agent],
        tasks=[t1_assemble, t2_draft],
        process=Process.sequential,
        verbose=verbose,
    )
    drafted_plan = str(draft_crew.kickoff(inputs={"query": query})).strip()

    plan = drafted_plan
    judge_json: Dict[str, Any] = {"ok": False, "expected": {}, "actual": {}, "errors": [], "fix_instructions": []}

    total_attempts = orig_max_iters + 1

    for attempt in range(1, total_attempts + 1):
        # ---------------- Judge ----------------
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

        # ---------------- Repair ----------------
        logger.info("[compiler] attempt=%d repairing plan", attempt)

        repair_crew = Crew(
            agents=[refiner_agent],
            tasks=[t4_repair_if_needed],
            process=Process.sequential,
            verbose=verbose,
        )

        # IMPORTANT: pass parsed judge JSON, not raw string
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
        orig_max_iters,
    )

    fallback = {
        "ok": False,
        "expected": {"message": "Valid workflow plan"},
        "actual": {"message": "Max repair attempts exceeded; returning raw query as output"},
        "errors": (judge_json.get("errors") or []) + [{"type": "MAX_RETRIES_EXCEEDED"}],
        "fix_instructions": [],
        "meta": {"fallback": True, "attempts": orig_max_iters},
    }
    return query, fallback
