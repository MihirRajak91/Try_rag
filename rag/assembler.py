# rag/assembler.py
import os
from dataclasses import dataclass
from typing import Dict, List, Union, Tuple
import hashlib

from rag.registry import ALL_CHUNKS
from rag.router import route, RoutingResult
from rag.support_expander import expand_support
from rag.prompt_audit import audit_prompt, PromptAudit
from rag.manifest import write_manifest
from rag import router as _router_cfg
 
# ----------------------------
# Caps (env-configurable)
# ----------------------------
MAX_PROMPT_TOKENS_APPROX = int(os.getenv("MAX_PROMPT_TOKENS_APPROX", "12000"))
MAX_ROUTER_BLOCKS = int(os.getenv("MAX_ROUTER_BLOCKS", "6"))
MAX_SUPPORT_BLOCKS = int(os.getenv("MAX_SUPPORT_BLOCKS", "12"))
MAX_CATALOG_BLOCKS = int(os.getenv("MAX_CATALOG_BLOCKS", "6"))
MANIFEST_SCHEMA_VERSION = 1

# ----------------------------
# Always-injected policy blocks
# ----------------------------
ALWAYS_TOPIC_HINTS = {
    # Adjust if your actual topic strings differ
    "router_disambiguation",
    "router_disambig",
    "disambiguation",
    "triggers_catalog",
    "trigger_catalog",
    "planner_policy",
    "triggers_rules",
    "output_contract"
}

class PromptTooLargeError(RuntimeError):
    pass


class PromptSectionCapError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExpansionResult:
    router_blocks: List[Dict]
    support_blocks: List[Dict]
    catalogs: List[Dict]


def _sort_by_priority_desc(chunks: List[Dict]) -> List[Dict]:
    return sorted(chunks, key=lambda c: int(c.get("priority", 0)), reverse=True)


def _dedupe_by_text(chunks: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for ch in chunks:
        txt = _norm_text(ch.get("text", ""))
        h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(ch)
    return out


def _norm_text(s: str) -> str:
    # normalize whitespace so substring checks are reliable
    return " ".join((s or "").strip().split())

def _drop_contained_blocks(chunks: List[Dict]) -> List[Dict]:
    """
    If chunk B's normalized text is fully contained within chunk A's normalized text,
    drop B (keep the more informative chunk).
    """
    normed = [(_norm_text(ch.get("text", "")), ch) for ch in chunks]
    out = []
    for i, (ti, chi) in enumerate(normed):
        if not ti:
            continue
        contained = False
        for j, (tj, _) in enumerate(normed):
            if i == j:
                continue
            if len(tj) >= len(ti) and ti in tj:
                contained = True
                break
        if not contained:
            out.append(chi)
    return out



def _is_always_block(ch: Dict) -> bool:
    t = str(ch.get("topic", "")).lower().strip()
    txt = str(ch.get("text", "")).lower()

    # 1) Prefer topic matches (fast + clean)
    if t in ALWAYS_TOPIC_HINTS:
        return True

    # 2) Fallback: match by distinctive headings/phrases in text
    # (works even if topic names differ)
    if "trigger" in txt and "catalog" in txt:
        return True
    if "planner output policy" in txt:
        return True
    if "disambiguation" in txt and "router" in txt:
        return True

    return False


def _select_always_blocks(all_chunks: List[Dict]) -> List[Dict]:
    blocks = [ch for ch in all_chunks if _is_always_block(ch)]
    return _dedupe_by_text(_sort_by_priority_desc(blocks))


def _expand_support_contract(topics: List[str]) -> ExpansionResult:
    selected_blocks = expand_support(topics)

    router_blocks = [ch for ch in selected_blocks if ch.get("role") == "router"]
    support_blocks = [ch for ch in selected_blocks if ch.get("role") == "support"]

    # Catalogs: any support chunk whose doc_type looks like a catalog
    catalogs = [
        ch for ch in support_blocks
        if str(ch.get("doc_type", "")).upper() in {"CATALOG", "CAT", "CATALOGS"}
        or str(ch.get("topic", "")).lower().startswith("catalog")
    ]

    # Keep catalogs out of general support list to avoid duplicates
    catalog_hashes = {hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() for ch in catalogs}
    support_blocks = [
        ch for ch in support_blocks
        if hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() not in catalog_hashes
    ]

    return ExpansionResult(
        router_blocks=router_blocks,
        support_blocks=support_blocks,
        catalogs=catalogs,
    )


def _enforce_caps(router_blocks: List[Dict], support_blocks: List[Dict], catalog_blocks: List[Dict]) -> None:
    if len(router_blocks) > MAX_ROUTER_BLOCKS:
        raise PromptSectionCapError(
            f"Router blocks cap exceeded: {len(router_blocks)} > {MAX_ROUTER_BLOCKS}. "
            f"(Set MAX_ROUTER_BLOCKS env var to increase.)"
        )
    if len(support_blocks) > MAX_SUPPORT_BLOCKS:
        raise PromptSectionCapError(
            f"Support blocks cap exceeded: {len(support_blocks)} > {MAX_SUPPORT_BLOCKS}. "
            f"(Set MAX_SUPPORT_BLOCKS env var to increase.)"
        )
    if len(catalog_blocks) > MAX_CATALOG_BLOCKS:
        raise PromptSectionCapError(
            f"Catalog blocks cap exceeded: {len(catalog_blocks)} > {MAX_CATALOG_BLOCKS}. "
            f"(Set MAX_CATALOG_BLOCKS env var to increase.)"
        )


def assemble_prompt(
    user_query: str,
    debug: bool = False,
    return_audit: bool = False,
    return_manifest: bool = False,
):
    # 1) CORE intro (static always)
    core_blocks = [
        ch for ch in ALL_CHUNKS
        if ch.get("role") == "static" and (
            ch.get("doc_type") == "CORE" or ch.get("topic") in {"core_intro", "intro", "core"}
        )
    ]
    core_blocks = _sort_by_priority_desc(core_blocks)

    # 1b) ALWAYS policy blocks (must be present like original planner)
    always_blocks = _select_always_blocks(ALL_CHUNKS)


    # 2) Router contract
    routing: RoutingResult = route(user_query, debug=debug)
    topics = list(routing.topics)

    # 3) Expand support via contract
    exp = _expand_support_contract(topics)

    router_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.router_blocks))
    support_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.support_blocks))
    catalog_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.catalogs))

    # Drop blocks that are contained inside other blocks (prevents partial duplicates)
    router_blocks = _drop_contained_blocks(router_blocks)
    support_blocks = _drop_contained_blocks(support_blocks)
    catalog_blocks = _drop_contained_blocks(catalog_blocks)

    # Cross-drop: if a support/catalog block is contained within any router block, drop it
    router_texts = [_norm_text(ch.get("text", "")) for ch in router_blocks]
    support_blocks = [
        ch for ch in support_blocks
        if not any(_norm_text(ch.get("text", "")) in rt for rt in router_texts if rt)
    ]
    catalog_blocks = [
        ch for ch in catalog_blocks
        if not any(_norm_text(ch.get("text", "")) in rt for rt in router_texts if rt)
    ]

    always_hashes = {
    hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest()
    for ch in always_blocks
}


    # cross-dedupe: don't include support/catalog blocks that repeat router blocks
    router_hashes = {hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() for ch in router_blocks}

    router_blocks = [
        ch for ch in router_blocks
        if hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest() not in always_hashes
    ]
    support_blocks = [
        ch for ch in support_blocks
        if hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest() not in always_hashes
    ]
    catalog_blocks = [
        ch for ch in catalog_blocks
        if hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest() not in always_hashes
    ] 

    # 4) Enforce section caps (after dedupe)
    _enforce_caps(router_blocks, support_blocks, catalog_blocks)

    # 5) Build prompt in strict order
    parts: List[str] = []
    chunks_in_order: List[Dict] = []

    for ch in core_blocks:
        parts.append(ch["text"].strip())
        chunks_in_order.append(ch)

    for ch in always_blocks:
        parts.append(ch["text"].strip())
        chunks_in_order.append(ch)

    for ch in router_blocks:
        parts.append(ch["text"].strip())
        chunks_in_order.append(ch)

    for ch in support_blocks:
        parts.append(ch["text"].strip())
        chunks_in_order.append(ch)

    for ch in catalog_blocks:
        parts.append(ch["text"].strip())
        chunks_in_order.append(ch)

    parts.append("USER.QUERY\n" + user_query.strip())

    # IMPORTANT: keep a raw prompt for audit/manifest (no debug header)
    final_prompt_raw = "\n\n---\n\n".join([p for p in parts if p])

    # 6) Enforce prompt-size cap (approx tokens)
    audit = audit_prompt(chunks_in_order=chunks_in_order, final_prompt=final_prompt_raw)
    if audit.approx_tokens > MAX_PROMPT_TOKENS_APPROX:
        raise PromptTooLargeError(
            f"Prompt token cap exceeded (approx): {audit.approx_tokens} > {MAX_PROMPT_TOKENS_APPROX}. "
            f"(Set MAX_PROMPT_TOKENS_APPROX env var to increase.)"
        )

    # 7) Optional manifest (based on raw prompt + chosen chunks)
    manifest = None
    if return_manifest:
        chunks_meta = []
        for ch in chunks_in_order:
            chunks_meta.append({
                "doc_type": ch.get("doc_type"),
                "topic": ch.get("topic"),
                "role": ch.get("role"),
                "priority": int(ch.get("priority", 0)),
                "source": ch.get("source"),
                "fingerprint": hashlib.sha1(ch.get("text", "").strip().encode("utf-8")).hexdigest(),
            })

        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "build_info": {
                "collection": getattr(_router_cfg, "COLLECTION_NAME", None),
                "embed_model": getattr(_router_cfg, "EMBED_MODEL", None),
                "chroma_dir": getattr(_router_cfg, "CHROMA_DIR", None),
            },
            "query": user_query,
            "routing": {
                "winner": routing.winner,
                "topics": list(routing.topics),
                "secondary": list(routing.secondary),
            },
            "audit": {
                "prompt_chars": audit.prompt_chars,
                "approx_tokens": audit.approx_tokens,
                "chunks_count": audit.chunks_count,
                "by_role": audit.by_role,
                "by_doc_type": audit.by_doc_type,
                "by_topic": audit.by_topic,
                "chunk_fingerprints": list(audit.chunk_fingerprints),
            },
            "chunks": chunks_meta,
        }


    # 8) Debug header only for printing/inspection
    final_prompt = final_prompt_raw
    if debug:
        topics_line = ", ".join(routing.topics) if routing.topics else "(none)"
        sec_line = ", ".join(routing.secondary) if routing.secondary else "(none)"
        final_prompt = (
            f"[debug] winner: {routing.winner or '(none)'}\n"
            f"[debug] secondary: {sec_line}\n"
            f"[debug] topics: {topics_line}\n"
            f"[debug] blocks: router={len(router_blocks)} support={len(support_blocks)} catalogs={len(catalog_blocks)}\n"
            f"[debug] approx_tokens={audit.approx_tokens} (cap={MAX_PROMPT_TOKENS_APPROX})\n\n"
            + final_prompt_raw
        )

    # 9) Return combinations
    if return_audit and return_manifest:
        return final_prompt, audit, manifest
    if return_audit:
        return final_prompt, audit
    if return_manifest:
        return final_prompt, manifest
    return final_prompt



def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return

    try:
        prompt, audit, manifest = assemble_prompt(
            q,
            debug=True,
            return_audit=True,
            return_manifest=True
        )

        path = write_manifest("manifests", manifest)

        print("\n=== MANIFEST SAVED ===")
        print(path)

        print("\n=== AUDIT ===")
        print(f"chars={audit.prompt_chars} approx_tokens={audit.approx_tokens} chunks={audit.chunks_count}")
        print(f"by_role={audit.by_role}")
        print(f"by_doc_type={audit.by_doc_type}")

        print("\n=== FINAL PROMPT ===\n")
        print(prompt)

    except (PromptTooLargeError, PromptSectionCapError) as e:
        print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    main()
