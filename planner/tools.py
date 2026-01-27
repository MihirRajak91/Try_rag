# planner/tools.py
import json
from typing import Any, Dict, List, Type

from pydantic import BaseModel, Field
from crewai.tools import BaseTool
from openai import OpenAI
import time
import logging

logger = logging.getLogger(__name__)

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
    debug: bool = Field(True, description="Include debug header in assembled prompt")
    save_manifest: bool = Field(True, description="Persist manifest to disk and return its path")


class AssemblePromptTool(BaseTool):
    name: str = "assemble_prompt"
    description: str = (
        "Routes the query, expands support, and assembles the final planner prompt. "
        "Returns compact JSON with prompt + audit summary + manifest_path."
    )
    args_schema: Type[BaseModel] = AssemblePromptInput

    def _run(self, query: str, debug: bool = True, save_manifest: bool = True) -> str:
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
        t_total = time.perf_counter()

        # ---- Normalize inputs defensively ----
        query = self._normalize(query)
        plan_markdown = self._normalize(plan_markdown)

        logger.info(
            "[judge_plan] start query_chars=%d plan_chars=%d model=%s",
            len(query),
            len(plan_markdown),
            JUDGE_MODEL,
        )

        # ---- Import judge context ----
        t_ctx = time.perf_counter()
        try:
            from planner.judge_context import (
                TRIGGERS_ENUMS,
                EVENT_ENUMS,
                CONDITION_ENUMS,
                LOOP_ENUMS,
                JUDGE_RULES,
            )
        except Exception:
            logger.exception("[judge_plan] context import failed")
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
        ctx_s = time.perf_counter() - t_ctx

        triggers = self._normalize(TRIGGERS_ENUMS)
        events = self._normalize(EVENT_ENUMS)
        conditions = self._normalize(CONDITION_ENUMS)
        loops = self._normalize(LOOP_ENUMS)
        rules = self._normalize(JUDGE_RULES)

        client = OpenAI()

        # ---- Build user prompt ----
        t_prompt = time.perf_counter()
        user_prompt = JUDGE_USER_TEMPLATE.format(
            query=query,
            plan=plan_markdown,
            triggers=triggers,
            events=events,
            conditions=conditions,
            loops=loops,
            rules=rules,
        )
        prompt_s = time.perf_counter() - t_prompt

        logger.info(
            "[judge_plan] built user_prompt_chars=%d ctx_s=%.3f prompt_build_s=%.3f",
            len(user_prompt),
            ctx_s,
            prompt_s,
        )

        # ---- Call judge model ----
        t_call = time.perf_counter()
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
            call_s = time.perf_counter() - t_call
            logger.exception("[judge_plan] OpenAI call failed call_s=%.3f", call_s)
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
        call_s = time.perf_counter() - t_call

        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None

        raw = (resp.choices[0].message.content or "").strip()

        logger.info(
            "[judge_plan] call_ok call_s=%.3f raw_chars=%d tokens(p=%s c=%s t=%s)",
            call_s,
            len(raw),
            str(prompt_tokens),
            str(completion_tokens),
            str(total_tokens),
        )

        # ---- Parse JSON ----
        t_parse = time.perf_counter()
        try:
            parsed = json.loads(raw)
        except Exception:
            parse_s = time.perf_counter() - t_parse
            logger.warning("[judge_plan] invalid_json parse_s=%.3f raw_prefix=%r", parse_s, raw[:200])
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
        parse_s = time.perf_counter() - t_parse

        # ---- Shape validation ----
        t_shape = time.perf_counter()
        try:
            JudgePlanResult(**parsed)
        except Exception as e:
            shape_s = time.perf_counter() - t_shape
            logger.warning("[judge_plan] invalid_schema shape_s=%.3f err=%s", shape_s, str(e))
            return json.dumps(
                {
                    "ok": False,
                    "expected": parsed.get("expected", {}) if isinstance(parsed, dict) else {},
                    "actual": parsed.get("actual", {}) if isinstance(parsed, dict) else {},
                    "errors": [{"type": "INVALID_JUDGE_SCHEMA", "message": str(e), "raw": parsed}],
                    "fix_instructions": ["Return JSON exactly matching the required schema."],
                },
                ensure_ascii=False,
            )
        shape_s = time.perf_counter() - t_shape

        # ---- Enum validation ----
        t_enum = time.perf_counter()
        try:
            validate_judge_output(parsed)
        except EnumValidationError as e:
            enum_s = time.perf_counter() - t_enum
            logger.warning("[judge_plan] enum_invalid enum_s=%.3f err=%s", enum_s, str(e))
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
        enum_s = time.perf_counter() - t_enum

        # ---- Existing invariant enforcement ----
        errors = parsed.get("errors") or []
        fix = self._clean_fix_list(parsed.get("fix_instructions"))
        parsed["fix_instructions"] = fix

        if parsed.get("ok") is False and len(errors) == 0 and len(fix) == 0:
            parsed["ok"] = True
        if parsed.get("ok") is False and len(errors) > 0 and len(fix) == 0:
            parsed["fix_instructions"] = [
                "Fix the plan to satisfy the judge errors using ONLY allowed enums and rules."
            ]

        total_s = time.perf_counter() - t_total
        logger.info(
            "[judge_plan] done ok=%s parse_s=%.3f shape_s=%.3f enum_s=%.3f total_s=%.3f",
            str(parsed.get("ok")),
            parse_s,
            shape_s,
            enum_s,
            total_s,
        )

        return json.dumps(parsed, ensure_ascii=False)

