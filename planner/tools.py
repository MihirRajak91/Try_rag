# planner/tools.py
import json
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

from rag.assembler import assemble_prompt
from rag.registry import ALL_CHUNKS
from rag.validator import validate_chunks
from rag.manifest import write_manifest
from rag.plan_validator import validate_plan_output



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