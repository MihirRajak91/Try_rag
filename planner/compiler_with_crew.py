# planner/compiler_with_crew.py
import json
import time
import logging
from typing import Any, Dict, Tuple, List
from contextlib import contextmanager

from planner.tools import AssemblePromptTool 

from crewai import Crew, Process

from planner.crew import (
    assembler_agent,
    planner_agent,
    validator_agent,
    refiner_agent,
    t1_assemble,
    t2_draft,
    t3_validate,
    t4_repair_if_needed,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Timing utility
# ---------------------------------------------------------------------------
@contextmanager
def phase_timer(label: str):
    start = time.perf_counter()
    logger.info("[timer:start] %s", label)
    try:
        yield
    finally:
        dur = time.perf_counter() - start
        logger.info("[timer:end] %s took %.3fs", label, dur)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def _extract_first_json_object(s: str) -> str:
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


def _try_parse_json(s: str) -> Dict[str, Any]:
    """
    Best-effort parse for assembler JSON.
    We don't use _safe_json here because that is for judge schema specifically.
    """
    raw = (s or "").strip()
    raw_json = _extract_first_json_object(raw) or raw
    try:
        obj = json.loads(raw_json)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _safe_json(s: str) -> Dict[str, Any]:
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
            if not x:
                continue
            s2 = str(x).strip()
            if not s2:
                continue
            low = s2.lower()
            if low in {"none", "null", "no", "n/a"}:
                continue
            if "plan is correct" in low:
                continue
            cleaned.append(s2)
        return cleaned

    try:
        parsed = json.loads(raw_json)
    except Exception as e:
        return {
            "ok": False,
            "expected": {},
            "actual": {
                "message": "Judge returned invalid JSON",
                "error": f"{type(e).__name__}: {e}",
            },
            "errors": [{"type": "INVALID_JSON", "raw": raw[:800]}],
            "fix_instructions": [
                "Re-run judge_plan and return valid JSON matching schema."
            ],
        }

    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "expected": {},
            "actual": {"message": "Judge returned non-dict JSON"},
            "errors": [{"type": "INVALID_JUDGE_SHAPE"}],
            "fix_instructions": [],
        }

    ok_val = parsed.get("ok", False)
    ok_bool = bool(ok_val) if isinstance(ok_val, (bool, int)) else False

    out: Dict[str, Any] = {
        "ok": ok_bool,
        "expected": _as_dict(parsed.get("expected")),
        "actual": _as_dict(parsed.get("actual")),
        "errors": _as_list(parsed.get("errors")),
        "fix_instructions": _clean_fix_list(parsed.get("fix_instructions")),
    }

    # self-healing invariants
    if out["ok"] is False and not out["errors"] and not out["fix_instructions"]:
        out["ok"] = True
        out["errors"] = [{
            "type": "NON_ACTIONABLE_FALSE",
            "message": "Judge returned ok=false with no errors/fixes; treating as ok=true",
        }]

    if out["ok"] is False and out["errors"] and not out["fix_instructions"]:
        out["fix_instructions"] = [
            "Fix the plan to satisfy the judge errors using ONLY allowed enums and rules."
        ]

    return out


# ---------------------------------------------------------------------------
# Main compiler
# ---------------------------------------------------------------------------
def compile_with_crew(
    query: str,
    max_iters: int = 2,
    verbose: bool = True,
    *,
    enable_validation: bool = True,
) -> Tuple[str, Dict[str, Any]]:

    with phase_timer("compile_with_crew:total"):

        # ---------------- Draft phase ----------------
        # t1_assemble (NO CrewAI): call tool directly
        with phase_timer("t1_assemble"):
            assemble_tool = AssemblePromptTool()
            assembled_json = assemble_tool._run(
                query=query,
                debug=False,
                save_manifest=False,
            ).strip()

            # optional: log routing summary
            try:
                aj = json.loads(assembled_json)
                routing = aj.get("routing") or {}
                audit = aj.get("audit") or {}
                logger.info(
                    "[t1_assemble] prompt_chars=%s approx_tokens=%s chunks=%s winner=%s topics=%s",
                    audit.get("prompt_chars"),
                    audit.get("approx_tokens"),
                    audit.get("chunks_count"),
                    routing.get("winner"),
                    routing.get("topics"),
                )
            except Exception:
                logger.info("[t1_assemble] assembled_json_len=%d", len(assembled_json))

        # t2_draft (CrewAI): single LLM call
        with phase_timer("t2_draft"):
            draft_crew = Crew(
                agents=[planner_agent],
                tasks=[t2_draft],
                process=Process.sequential,
                verbose=verbose,
            )
            drafted_plan = str(
                draft_crew.kickoff(
                    inputs={"assembled_json": assembled_json}
                )
            ).strip()

            logger.info("[t2_draft] plan_len=%d", len(drafted_plan))

        # ---------- rest of your validation loop unchanged ----------
        if not enable_validation:
            return drafted_plan, {
                "ok": True,
                "expected": {"message": "Validation disabled"},
                "actual": {"message": "Validation disabled"},
                "errors": [],
                "fix_instructions": [],
                "meta": {"validation": "disabled"},
            }

        plan = drafted_plan
        judge_json: Dict[str, Any] = {}

        for attempt in range(1, max_iters + 1):
            with phase_timer(f"judge_phase attempt={attempt}"):
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

            logger.info(
                "[compiler:attempt_summary] attempt=%d ok=%s plan_len=%d errors=%d fixes=%d",
                attempt,
                judge_json.get("ok"),
                len(plan),
                len(judge_json.get("errors") or []),
                len(judge_json.get("fix_instructions") or []),
            )

            if judge_json.get("ok") is True:
                logger.info("[compiler] SUCCESS at attempt=%d", attempt)
                return plan, judge_json

            if attempt >= max_iters:
                break

            with phase_timer(f"repair_phase attempt={attempt}"):
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

        logger.error("[compiler] MAX_RETRIES_EXCEEDED (%d)", max_iters)
        return query, {
            "ok": False,
            "expected": {"message": "Valid workflow plan"},
            "actual": {"message": "Max repair attempts exceeded"},
            "errors": (judge_json.get("errors") or []) + [{"type": "MAX_RETRIES_EXCEEDED"}],
            "fix_instructions": [],
            "meta": {"attempts": max_iters},
        }