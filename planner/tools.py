# planner/tools.py
import json
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from openai import OpenAI

from rag.assembler import assemble_prompt
from rag.registry import ALL_CHUNKS
from rag.validator import validate_chunks
from rag.manifest import write_manifest
from rag.plan_validator import validate_plan_output
from rag.judge_prompt import JUDGE_SYSTEM_PROMPT, JUDGE_USER_TEMPLATE
from planner.model_config import JUDGE_MODEL
from rag.enum_guard import validate_judge_output, EnumValidationError


# -------------------------
# Assemble Prompt Tool
# -------------------------
class AssemblePromptInput(BaseModel):
    query: str = Field(..., description="User workflow request")
    debug: bool = Field(False, description="Include debug header in assembled prompt")
    save_manifest: bool = Field(True, description="Persist manifest to disk and return its path")


class AssemblePromptTool(BaseTool):
    name: str = "assemble_prompt"
    description: str = (
        "Routes the query, expands support, and assembles the final planner prompt. "
        "Returns compact JSON with prompt + audit summary + manifest_path."
    )
    args_schema: Type[BaseModel] = AssemblePromptInput

    def _run(self, query: str, debug: bool = False, save_manifest: bool = True) -> str:
        # Validate chunk registry once per run
        validate_chunks(ALL_CHUNKS)

        prompt, audit, manifest = assemble_prompt(
            query,
            debug=debug,
            return_audit=True,
            return_manifest=True,
        )

        manifest_path = None
        if save_manifest and manifest:
            manifest_path = write_manifest("manifests", manifest)

        payload = {
            "prompt": prompt,
            "audit": {
                "prompt_chars": audit.prompt_chars,
                "approx_tokens": audit.approx_tokens,
                "chunks_count": audit.chunks_count,
            },
            "routing": (manifest or {}).get("routing", {}),
            "manifest_path": manifest_path,
        }
        return json.dumps(payload, ensure_ascii=False)


# -------------------------
# Validate Plan Tool
# -------------------------
class ValidatePlanInput(BaseModel):
    plan_markdown: str = Field(..., description="The drafted workflow plan in Markdown")


class ValidatePlanTool(BaseTool):
    name: str = "validate_plan"
    description: str = "Validates the drafted Markdown workflow plan against the output contract."
    args_schema: Type[BaseModel] = ValidatePlanInput

    def _run(self, plan_markdown: str) -> str:
        result = validate_plan_output(plan_markdown)
        return json.dumps(result, ensure_ascii=False)


# -------------------------
# Judge Plan Tool
# -------------------------
class JudgePlanInput(BaseModel):
    query: str = Field(..., description="Original user query")
    plan_markdown: str = Field(..., description="Generated workflow plan in Markdown")


class JudgePlanResult(BaseModel):
    ok: bool
    expected: Dict[str, Any]
    actual: Dict[str, Any]
    errors: List[Any]
    fix_instructions: List[str]


class JudgePlanTool(BaseTool):
    name: str = "judge_plan"
    description: str = (
        "Return ONLY a JSON object string with keys: ok, expected, actual, errors, fix_instructions. "
        "No commentary."
    )
    args_schema: Type[BaseModel] = JudgePlanInput


    def _normalize(self, v: Any) -> str:
        """
        Crew/agents sometimes pass schema-like dicts such as:
          {"description": "...", "type": "str"}
        Normalize to a plain string.
        """
        if isinstance(v, dict):
            return v.get("description") or v.get("value") or json.dumps(v, ensure_ascii=False)
        return "" if v is None else str(v)

    def _clean_fix_list(self, fix: Any) -> List[str]:
        """
        Remove junk "fixes" like:
          - "None"
          - "plan is correct"
          - praise text
          - empty strings
        """
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
            s = str(x).strip()
            if not s:
                continue
            low = s.lower()

            if low in {"none", "null", "no", "n/a"}:
                continue
            if "plan is correct" in low:
                continue
            if "appropriate trigger" in low:
                continue

            cleaned.append(s)

        return cleaned

    def _run(self, query: str, plan_markdown: str) -> str:
        # ---- Normalize inputs defensively ----
        query = self._normalize(query)
        plan_markdown = self._normalize(plan_markdown)

        logger.info("[judge_plan] TOOL INVOKED")

        try:
            from planner.judge_context import (
                TRIGGERS_ENUMS,
                EVENT_ENUMS,
                CONDITION_ENUMS,
                LOOP_ENUMS,
                JUDGE_RULES,
            )
        except Exception:
            # If you keep enums in different modules, change imports above.
            # Fail loudly with a helpful error.
            return json.dumps(
                {
                    "ok": False,
                    "expected": {},
                    "actual": {},
                    "errors": [
                        {
                            "type": "JUDGE_CONTEXT_IMPORT_FAILED",
                            "message": "Could not import judge enums/rules. Update import path in JudgePlanTool.",
                        }
                    ],
                    "fix_instructions": [
                        "Fix JudgePlanTool imports so it can inject allowed enums/rules internally."
                    ],
                },
                ensure_ascii=False,
            )

        triggers = self._normalize(TRIGGERS_ENUMS)
        events = self._normalize(EVENT_ENUMS)
        conditions = self._normalize(CONDITION_ENUMS)
        loops = self._normalize(LOOP_ENUMS)
        rules = self._normalize(JUDGE_RULES)

        client = OpenAI()

        user_prompt = JUDGE_USER_TEMPLATE.format(
            query=query,
            plan=plan_markdown,
            triggers=triggers,
            events=events,
            conditions=conditions,
            loops=loops,
            rules=rules,
        )

        # ---- Call judge model ----
        try:
            resp = client.chat.completions.create(
                model=JUDGE_MODEL,
                temperature=0,
                max_tokens=1200,
                timeout=30,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            return json.dumps(
                {
                    "ok": False,
                    "expected": {},
                    "actual": {},
                    "errors": [
                        {"type": "JUDGE_CALL_FAILED", "message": f"{type(e).__name__}: {e}"}
                    ],
                    "fix_instructions": ["Retry judge call (tool failure)."],
                },
                ensure_ascii=False,
            )

        raw = (resp.choices[0].message.content or "").strip()

        # ---- HARD SAFETY: JSON parse ----
        try:
            parsed = json.loads(raw)
        except Exception:
            return json.dumps(
                {
                    "ok": False,
                    "expected": {},
                    "actual": {},
                    "errors": [
                        {
                            "type": "INVALID_JUDGE_OUTPUT",
                            "message": "Judge did not return valid JSON",
                            "raw": raw[:500],
                        }
                    ],
                    "fix_instructions": [
                        "Re-evaluate the plan strictly using the provided rules and output valid JSON only."
                    ],
                },
                ensure_ascii=False,
            )

        # ---- SHAPE VALIDATION (STRICT) ----
        try:
            JudgePlanResult(**parsed)
        except Exception as e:
            return json.dumps(
                {
                    "ok": False,
                    "expected": parsed.get("expected", {}) if isinstance(parsed, dict) else {},
                    "actual": parsed.get("actual", {}) if isinstance(parsed, dict) else {},
                    "errors": [
                        {"type": "INVALID_JUDGE_SCHEMA", "message": str(e), "raw": parsed}
                    ],
                    "fix_instructions": ["Return JSON exactly matching the required schema."],
                },
                ensure_ascii=False,
            )

        # ---- ENUM VALIDATION (FAIL FAST) ----
        try:
            validate_judge_output(parsed)
        except EnumValidationError as e:
            return json.dumps(
                {
                    "ok": False,
                    "expected": parsed.get("expected", {}),
                    "actual": parsed.get("actual", {}),
                    "errors": [
                        {
                            "type": "INVALID_ENUM_IN_PLAN",
                            "expected": "Trigger must be one of allowed TRG_* enums",
                            "found": str(e),
                            "rule_ref": "ENUM SAFETY",
                        }
                    ],
                    "fix_instructions": [
                        "Replace the Trigger with TRG_DB unless the query explicitly requires another allowed trigger.",
                        "Do not invent new TRG_* enums; use only the allowed trigger list provided.",
                    ],
                },
                ensure_ascii=False,
            )

        # ---- INVARIANT ENFORCEMENT ----
        errors = parsed.get("errors") or []
        fix = self._clean_fix_list(parsed.get("fix_instructions"))

        # always write cleaned list back
        parsed["fix_instructions"] = fix

        # If ok=false but there are no actionable errors AND no actionable fixes => treat as ok=true
        if parsed.get("ok") is False and len(errors) == 0 and len(fix) == 0:
            parsed["ok"] = True

        # If ok=false and errors exist but fixes empty => force a generic fix so refiner can act
        if parsed.get("ok") is False and len(errors) > 0 and len(fix) == 0:
            parsed["fix_instructions"] = [
                "Fix the plan to satisfy the judge errors using ONLY allowed enums and rules."
            ]

        return json.dumps(parsed, ensure_ascii=False)
