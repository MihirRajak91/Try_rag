import os
from typing import Dict, Any
from openai import OpenAI

from rag.assembler import assemble_prompt
from rag.manifest import write_manifest


def run_planner_full(query: str, debug: bool = True) -> Dict[str, Any]:
    prompt, audit, manifest = assemble_prompt(
        query,
        debug=debug,
        return_audit=True,
        return_manifest=True,
    )

    manifest_path = write_manifest("manifests", manifest)

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        messages=[
            {"role": "system", "content": "You are an expert workflow automation architect."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    output = resp.choices[0].message.content.strip()

    return {
        "routing": manifest.get("routing", {}),
        "audit": {
            "prompt_chars": audit.prompt_chars,
            "approx_tokens": audit.approx_tokens,
            "chunks_count": audit.chunks_count,
            "by_role": audit.by_role,
            "by_doc_type": audit.by_doc_type,
            "by_topic": audit.by_topic,
        },
        "manifest_path": manifest_path,
        "manifest": manifest,
        "prompt": prompt,
        "llm_output": output,
    }
