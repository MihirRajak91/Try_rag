# rag/prompt_audit.py
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()


def approx_token_count(text: str) -> int:
    """
    Stable heuristic (no tokenizer dependency).
    Rule of thumb: ~4 characters per token in English-ish text.
    """
    t = (text or "").strip()
    if not t:
        return 0
    return max(1, len(t) // 4)


@dataclass(frozen=True)
class PromptAudit:
    prompt_chars: int
    approx_tokens: int
    chunks_count: int
    by_role: Dict[str, int]
    by_doc_type: Dict[str, int]
    by_topic: Dict[str, int]
    chunk_fingerprints: Tuple[str, ...]  # stable order


def audit_prompt(chunks_in_order: List[Dict], final_prompt: str) -> PromptAudit:
    by_role: Dict[str, int] = {}
    by_doc_type: Dict[str, int] = {}
    by_topic: Dict[str, int] = {}
    fps: List[str] = []

    for ch in chunks_in_order:
        role = str(ch.get("role", ""))
        dt = str(ch.get("doc_type", ""))
        topic = str(ch.get("topic", ""))

        by_role[role] = by_role.get(role, 0) + 1
        by_doc_type[dt] = by_doc_type.get(dt, 0) + 1
        by_topic[topic] = by_topic.get(topic, 0) + 1

        fps.append(_sha1(ch.get("text", "")))

    return PromptAudit(
        prompt_chars=len(final_prompt or ""),
        approx_tokens=approx_token_count(final_prompt or ""),
        chunks_count=len(chunks_in_order),
        by_role=by_role,
        by_doc_type=by_doc_type,
        by_topic=by_topic,
        chunk_fingerprints=tuple(fps),
    )
