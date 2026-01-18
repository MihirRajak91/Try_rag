# rag/registry.py
from collections import defaultdict
from typing import Dict, List, Tuple

from data.rag_chunks_data_clean import chunk_data as CLEAN_CHUNKS

# rag/registry.py
from typing import Dict, List, Tuple

from data.rag_chunks_data_clean import chunk_data as CLEAN_CHUNKS

def _load_legacy_chunks():
    try:
        import data.rag_chunks as legacy
    except Exception:
        return []
    for name in ("CHUNKS", "chunk_data", "chunks", "RAG_CHUNKS"):
        if hasattr(legacy, name) and isinstance(getattr(legacy, name), list):
            return getattr(legacy, name)
    return []

LEGACY_CHUNKS = _load_legacy_chunks()

def _chunk_key(chunk: Dict) -> Tuple:
    """
    Identity key for merging chunks.
    """
    return (
        chunk.get("doc_type"),
        chunk.get("topic"),
        chunk.get("role"),
    )


def _normalize_chunk(chunk: Dict, source: str) -> Dict:
    """
    Normalize any chunk to the locked contract.
    """
    return {
        "doc_type": chunk["doc_type"],
        "topic": chunk["topic"],
        "priority": int(chunk["priority"]),
        "role": chunk["role"],
        "data": chunk["data"].strip(),
        "text": chunk["text"].strip(),
        "source": source,
    }


def build_registry():
    merged: Dict[Tuple, Dict] = {}
    report = {
        "clean_count": 0,
        "legacy_count": 0,
        "merged_count": 0,
        "legacy_overrides": [],
    }

    # 1) Load clean chunks first (authoritative)
    for ch in CLEAN_CHUNKS:
        key = _chunk_key(ch)
        merged[key] = _normalize_chunk(ch, source="clean")
        report["clean_count"] += 1

    # 2) Merge legacy chunks (fill gaps only)
    for ch in LEGACY_CHUNKS:
        key = _chunk_key(ch)
        report["legacy_count"] += 1

        normalized = _normalize_chunk(ch, source="legacy")

        if key not in merged:
            merged[key] = normalized
        else:
            existing = merged[key]
            # clean-first, legacy-fill
            if len(existing["text"]) < len(normalized["text"]):
                existing["text"] = normalized["text"]
                report["legacy_overrides"].append(key)

    report["merged_count"] = len(merged)
    return list(merged.values()), report


ALL_CHUNKS, BUILD_REPORT = build_registry()
