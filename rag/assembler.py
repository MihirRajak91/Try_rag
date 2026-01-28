import os
import re
import hashlib
import time
import logging
from dataclasses import dataclass
from typing import Dict, List

from rag.registry import ALL_CHUNKS
from rag.router import route, RoutingResult
from rag.support_expander import expand_support
from rag.prompt_audit import audit_prompt, PromptAudit
from rag.manifest import write_manifest
from rag import router as _router_cfg

logger = logging.getLogger(__name__)

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
    "router_disambiguation",
    "router_disambig",
    "disambiguation",
    "triggers_catalog",
    "trigger_catalog",
    "planner_policy",
    "triggers_rules",
    "output_contract",
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


class _Timer:
    def __init__(self):
        self.start = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.start


# def _has_explicit_branching(q: str) -> bool:
#     t = set(q.lower().replace(",", " ").replace(".", " ").split())
#     return ("else" in t) or ("otherwise" in t) or ("unless" in t)


def _sort_by_priority_desc(chunks: List[Dict]) -> List[Dict]:
    return sorted(chunks, key=lambda c: int(c.get("priority", 0)), reverse=True)


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split())


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


# def _has_condition_language(q: str) -> bool:
#     s = (q or "").lower()
#     if any(w in s for w in ["check if", "verify if", "if not", "else check", "otherwise", "unless"]):
#         return True
#     return len(re.findall(r"\bif\b", s)) >= 2


# def _has_seq_language(q: str) -> bool:
#     s = (q or "").lower()
#     return bool(re.search(r"\band\b.*\b(check|verify)?\s*if\b", s))


# def has_dom_language(q: str) -> bool:
#     s = (q or "").lower()
#     s = re.sub(r"[,.]", "", s)
#     s = " ".join(s.split())
#     dom_connectors = ["first check", "if not then", "else check if", "if fails", "if fails try", "try"]
#     pattern = r"|".join(re.escape(k) for k in dom_connectors)
#     splits = [seg.strip() for seg in re.split(pattern, s) if seg.strip()]
#     return len(splits) >= 2


def _drop_contained_blocks(chunks: List[Dict]) -> List[Dict]:
    normed = [(_norm_text(ch.get("text", "")), ch) for ch in chunks]
    out: List[Dict] = []
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

    if t in ALWAYS_TOPIC_HINTS:
        return True

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


def _expand_support_contract(topics: List[str], winner: str | None = None) -> ExpansionResult:
    selected_blocks = expand_support(topics, winner=winner)

    router_blocks = [ch for ch in selected_blocks if ch.get("role") == "router"]
    support_blocks = [ch for ch in selected_blocks if ch.get("role") == "support"]

    catalogs = [
        ch for ch in support_blocks
        if str(ch.get("doc_type", "")).upper() in {"CATALOG", "CAT", "CATALOGS"}
        or str(ch.get("topic", "")).lower().startswith("catalog")
    ]

    catalog_hashes = {hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() for ch in catalogs}
    support_blocks = [
        ch for ch in support_blocks
        if hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() not in catalog_hashes
    ]

    return ExpansionResult(router_blocks=router_blocks, support_blocks=support_blocks, catalogs=catalogs)


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
    asm_timer = _Timer()
    timings: Dict[str, float] = {}

    # 1) CORE intro + ALWAYS
    t_core = _Timer()
    core_blocks = [
        ch for ch in ALL_CHUNKS
        if ch.get("role") == "static"
        and (ch.get("doc_type") == "CORE" or ch.get("topic") in {"core_intro", "intro", "core"})
    ]
    core_blocks = _sort_by_priority_desc(core_blocks)
    always_blocks = _select_always_blocks(ALL_CHUNKS)
    timings["core_always_s"] = t_core.elapsed()

    # 2) Router contract
    t_router = _Timer()
    routing: RoutingResult = route(user_query, debug=debug)
    topics = list(routing.topics)
    timings["router_call_s"] = t_router.elapsed()

    # FORCE include conditions topic when language appears
    # if _has_condition_language(user_query) and "conditions" not in topics:
    #     topics.append("conditions")

    # 3) Expand support
    t_expand = _Timer()
    exp = _expand_support_contract(topics, winner=routing.winner)

    if debug:
        print("[assembler] allowed_topics:", topics)
        print("[assembler] exp.router_topics:", sorted({c.get("topic") for c in exp.router_blocks}))
        print("[assembler] exp.support_topics:", sorted({c.get("topic") for c in exp.support_blocks}))

    timings["expand_support_s"] = t_expand.elapsed()

    # 4) dedupe/drop
    t_dedupe = _Timer()

    router_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.router_blocks))
    support_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.support_blocks))
    catalog_blocks = _dedupe_by_text(_sort_by_priority_desc(exp.catalogs))

    router_blocks = _drop_contained_blocks(router_blocks)
    support_blocks = _drop_contained_blocks(support_blocks)
    catalog_blocks = _drop_contained_blocks(catalog_blocks)

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

    timings["dedupe_drop_s"] = t_dedupe.elapsed()

    # 5) caps
    _enforce_caps(router_blocks, support_blocks, catalog_blocks)

    # 6) build prompt
    t_prompt = _Timer()
    parts: List[str] = []
    chunks_in_order: List[Dict] = []

    for ch in core_blocks:
        parts.append(ch["text"].strip()); chunks_in_order.append(ch)
    for ch in always_blocks:
        parts.append(ch["text"].strip()); chunks_in_order.append(ch)
    for ch in router_blocks:
        parts.append(ch["text"].strip()); chunks_in_order.append(ch)
    for ch in support_blocks:
        parts.append(ch["text"].strip()); chunks_in_order.append(ch)
    for ch in catalog_blocks:
        parts.append(ch["text"].strip()); chunks_in_order.append(ch)

    parts.append("USER.QUERY\n" + user_query.strip())
    final_prompt_raw = "\n\n---\n\n".join([p for p in parts if p])
    timings["prompt_build_s"] = t_prompt.elapsed()

    # 7) audit
    t_audit = _Timer()
    audit: PromptAudit = audit_prompt(chunks_in_order=chunks_in_order, final_prompt=final_prompt_raw)
    timings["audit_s"] = t_audit.elapsed()

    if audit.approx_tokens > MAX_PROMPT_TOKENS_APPROX:
        raise PromptTooLargeError(
            f"Prompt token cap exceeded (approx): {audit.approx_tokens} > {MAX_PROMPT_TOKENS_APPROX}. "
            f"(Set MAX_PROMPT_TOKENS_APPROX env var to increase.)"
        )

    # 8) manifest
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
                "fingerprint": hashlib.sha1((ch.get("text", "") or "").strip().encode("utf-8")).hexdigest(),
            })

        timings["assembler_total_s"] = asm_timer.elapsed()

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
                "topics": list(topics),
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
            "timing": {
                **timings,
                **(routing.timing or {}),
            },
        }

    # 9) debug header only for printing/inspection
    final_prompt = final_prompt_raw
    if debug:
        topics_line = ", ".join(topics) if topics else "(none)"
        sec_line = ", ".join(routing.secondary) if routing.secondary else "(none)"
        final_prompt = (
            f"[debug] winner: {routing.winner or '(none)'}\n"
            f"[debug] secondary: {sec_line}\n"
            f"[debug] topics: {topics_line}\n"
            f"[debug] blocks: router={len(router_blocks)} support={len(support_blocks)} catalogs={len(catalog_blocks)}\n"
            f"[debug] approx_tokens={audit.approx_tokens} (cap={MAX_PROMPT_TOKENS_APPROX})\n\n"
            + final_prompt_raw
        )

    # enforcement blocks (keep your existing behavior)
#     if _has_explicit_branching(user_query):
#         final_prompt += """

# ---
# BRANCHING ENFORCEMENT (HARD RULES)

# The user query contains an explicit ELSE/OTHERWISE/UNLESS, so branching is REQUIRED.

# You MUST:
# 1) Use ## Conditions with exactly one ### CNDN_BIN.
# 2) Include BOTH branches:
# - IF TRUE: ↳ <EVNT_* ...>
# - IF FALSE: ↳ <EVNT_* ...>
# 3) In ## Steps, do NOT write any freeform "IF ..." text.
# - ## Steps must contain ONLY numbered codes.
# - For this case, ## Steps must be:
#     1. CNDN_BIN

# If you violate any rule above, your output is invalid.
# """

#     if _has_seq_language(user_query) and not _has_explicit_branching(user_query):
#         final_prompt += """

# ---
# SEQUENCE CONDITION ENFORCEMENT (HARD RULES)

# The user query contains MULTIPLE INDEPENDENT conditions connected by AND, so CNDN_SEQ is REQUIRED.

# You MUST:
# 1) In ## Steps, include EXACTLY:
# 1. CNDN_SEQ

# 2) Create a ## Conditions section with exactly:
# ### CNDN_SEQ

# 3) Under ### CNDN_SEQ, write one logic block per independent check using this shape:
# - ↳ (CNDN_LGC) <condition>:
#   ↳ <EVNT_* ...>

# 4) DO NOT write any freeform "IF ... THEN ..." lines in ## Steps.

# If you violate any rule above, your output is invalid.
# """

#     if has_dom_language(user_query) and not _has_explicit_branching(user_query) and not _has_seq_language(user_query):
#         final_prompt += """

# ---
# DOMINO CASCADING CONDITION ENFORCEMENT (HARD RULES)

# The user query contains cascading checks (first check / if not then / else check if / if fails),
# so CNDN_DOM is REQUIRED.

# You MUST:
# 1) In ## Steps, include EXACTLY:
#     1. CNDN_DOM

# 2) Create a ## Conditions section with one CNDN_LGC_DOM container per sequential condition.

# 3) Under each ### CNDN_LGC_DOM container, follow this shape:
#     - IF: ↳ <EVNT_* ...>
#     - ELSE: ↳ route to next container or → END

# 4) DO NOT write any freeform "IF ... THEN ..." lines in ## Steps.

# If you violate any rule above, your output is invalid.
# """
    if "conditions" in topics:
        final_prompt += """

---
CONDITIONS ENFORCEMENT (HARD RULES)

You MUST output a Markdown plan with these EXACT section headers (including the ## symbols):
## Trigger
## Start
## Steps
## Conditions
## End

Under each section, you MUST follow these exact rules:

- Under ## Trigger:
  - Output EXACTLY one bullet line in this format:
    - TRG_*

- Under ## Start:
  - Output EXACTLY:
    - Start
  - Do NOT write condition checks or logic here.

- Under ## End:
  - Output EXACTLY:
    - End


If conditional logic is required, you MUST:
1) In ## Steps, output EXACTLY ONE line:
1. CNDN_BIN   OR  1. CNDN_SEQ   OR  1. CNDN_DOM

2) In ## Conditions, output EXACTLY ONE matching subheader (including ###):
### CNDN_BIN  OR  ### CNDN_SEQ  OR  ### CNDN_DOM

3) Do NOT repeat any EVNT_* in ## Steps if it appears in ## Conditions.

CNDN_SEQ FORMAT (REQUIRED):
### CNDN_SEQ
- Logic Block 1:
  ↳ IF TRUE: <EVNT_* ...>
  ↳ IF FALSE: Route to END
- Logic Block 2:
  ↳ IF TRUE: <EVNT_* ...>
  ↳ IF FALSE: Route to END

CNDN_BIN FORMAT (REQUIRED):
### CNDN_BIN
- IF TRUE:
  ↳ <EVNT_* ...>
- IF FALSE:
  ↳ <EVNT_* ...> OR Route to END

CNDN_DOM FORMAT (REQUIRED):
### CNDN_DOM
- Container 1:
  ↳ IF TRUE: <EVNT_* ...>
  ↳ IF FALSE: Route to Container 2
- Container 2:
  ↳ IF TRUE: <EVNT_* ...>
  ↳ IF FALSE: Route to END

If you violate any rule above, the output is invalid.
"""

    # ---- LOOP DEDUPE ENFORCEMENT (topic-based; no keyword detection) ----
    if "loops" in topics:
        final_prompt += """

---
LOOPS ENFORCEMENT (HARD RULES)

The router selected the "loops" topic, so repetition is REQUIRED.

You MUST:
1) Include a ## Loops section.
2) Express the repetition count explicitly:
   - If the query says "N times" or "repeat N", the loop MUST include count: N.
3) Format inside ## Loops with NO numbered lines:
   - Use ONLY bullet format:
     - EVNT_LOOP_FOR (count: N)
       ↳ INSIDE LOOP: <EVNT_* ...>
4) DO NOT repeat the looped action in ## Steps.
5) If there are no top-level steps outside loops, OMIT the ## Steps section entirely.

If you violate any rule above, your output is invalid.

"""

    if "conditions" in topics:
        final_prompt += """

    ---
    CONDITIONS ENFORCEMENT (HARD RULES)

    The router selected the "conditions" topic, so conditional logic is REQUIRED.

    You MUST:
    1) Include a ## Conditions section with exactly ONE of:
    - ### CNDN_BIN  (if/else branching)
    - ### CNDN_SEQ  (parallel independent checks)
    - ### CNDN_DOM  (cascading fallback checks)

    2) ## Steps must contain ONLY the condition code (and nothing else):
    1. CNDN_BIN   OR
    1. CNDN_SEQ   OR
    1. CNDN_DOM

    3) Do NOT include EVNT_* actions as numbered Steps when they appear inside ## Conditions.
    (No duplication between ## Steps and ## Conditions.)

    If you violate any rule above, your output is invalid.

    If the query is only checks (no explicit action like email/sms/create/update/etc), then the branches route to END (or “continue”), and do not invent notifications.

    Example expectation:

    CNDN_DOM containers:

    IF quota ok → END

    ELSE → check plan

    IF plan ok → END

    ELSE → END


    """


    # ✅ PRINT timings always (works with your current print-based runner)
    timings["assembler_total_s"] = asm_timer.elapsed()
    print(
        "[timing] assembler "
        f"core_always={timings.get('core_always_s', 0):.6f}s "
        f"router_call={timings.get('router_call_s', 0):.6f}s "
        f"expand_support={timings.get('expand_support_s', 0):.6f}s "
        f"dedupe_drop={timings.get('dedupe_drop_s', 0):.6f}s "
        f"prompt_build={timings.get('prompt_build_s', 0):.6f}s "
        f"audit={timings.get('audit_s', 0):.6f}s "
        f"total={timings.get('assembler_total_s', 0):.6f}s"
    )

    if routing.timing:
        # embed/chroma/centroid/router_total from router
        rt = routing.timing
        print(
            "[timing] router "
            f"embed={rt.get('embed_s', 0):.3f}s "
            f"chroma={rt.get('chroma_s', 0):.3f}s "
            f"centroid={rt.get('centroid_s', 0):.3f}s "
            f"total={rt.get('router_total_s', 0):.3f}s"
        )

    # 10) Return combinations
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
            return_manifest=True,
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
