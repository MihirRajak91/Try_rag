# planner/tools.py
import json
from typing import Type
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


class ValidatePlanInput(BaseModel):
    plan_markdown: str = Field(..., description="The drafted workflow plan in Markdown")

class ValidatePlanTool(BaseTool):
    name: str = "validate_plan"
    description: str = "Validates the drafted Markdown workflow plan against the output contract."
    args_schema: Type[BaseModel] = ValidatePlanInput

    def _run(self, plan_markdown: str) -> str:
        result = validate_plan_output(plan_markdown)
        return json.dumps(result, ensure_ascii=False)


class JudgePlanInput(BaseModel):
    query: str = Field(..., description="Original user query")
    plan_markdown: str = Field(..., description="Generated workflow plan in Markdown")
    triggers: str
    events: str
    conditions: str
    loops: str
    rules: str

class JudgePlanResult(BaseModel):
    ok: bool

    expected: dict
    actual: dict

    errors: list
    fix_instructions: list



class JudgePlanTool(BaseTool):
    name: str = "judge_plan"
    description: str = "Judges whether the workflow plan is correct and returns structured JSON."
    args_schema: Type[BaseModel] = JudgePlanInput

    def _run(
        self,
        query: str,
        plan_markdown: str,
        triggers: str,
        events: str,
        conditions: str,
        loops: str,
        rules: str,
    ) -> str:
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

        raw = resp.choices[0].message.content.strip()

        # --- HARD SAFETY ---
        try:
            parsed = json.loads(raw)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "errors": [{
                    "type": "INVALID_JUDGE_OUTPUT",
                    "message": "Judge did not return valid JSON",
                    "raw": raw[:500]
                }],
                "fix_instructions": [
                    "Re-evaluate the plan strictly using the provided rules and output valid JSON only."
                ]
            })

        # --- SHAPE VALIDATION ---
        try:
            JudgePlanResult(**parsed)
        except Exception as e:
            return json.dumps({
                "ok": False,
                "errors": [{
                    "type": "INVALID_JUDGE_SCHEMA",
                    "message": str(e),
                    "raw": parsed
                }],
                "fix_instructions": [
                    "Return JSON exactly matching the required schema."
                ]
            }, ensure_ascii=False)

        # --- ENUM VALIDATION (FAIL FAST) ---
        try:
            validate_judge_output(parsed)
        except EnumValidationError as e:
            return json.dumps({
                "ok": False,
                "expected": parsed.get("expected", {}),
                "actual": parsed.get("actual", {}),
                "errors": [{
                    "type": "INVALID_ENUM_IN_PLAN",
                    "expected": "Trigger must be one of allowed TRG_* enums",
                    "found": str(e),
                    "rule_ref": "ENUM SAFETY"
                }],
                "fix_instructions": [
                    "Replace the Trigger with TRG_DB unless the query explicitly requires another trigger.",
                    "Do not use TRG_NOTI (invalid)."
                ]
            }, ensure_ascii=False)



