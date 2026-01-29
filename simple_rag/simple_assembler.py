import argparse
import os
import hashlib
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI

from data.rag_chunks_data_clean import chunk_data

load_dotenv()

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", os.getenv("CHROMA_DIR", ".chroma"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_chunks_v1")
EMBED_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", os.getenv("EMBED_MODEL", "text-embedding-3-small"))
TOP_K = int(os.getenv("QUERY_TOP_K", "8"))
MAX_BLOCKS = int(os.getenv("SIMPLE_RAG_MAX_BLOCKS", "10"))
LOOPS_MAX_ABS_GAP = float(os.getenv("SIMPLE_RAG_LOOPS_MAX_ABS_GAP", "0.02"))
CONDITIONS_MAX_ABS_GAP = float(os.getenv("SIMPLE_RAG_CONDITIONS_MAX_ABS_GAP", "0.05"))
CONDITIONS_MIN_GAP_OVER_ACTIONS = float(os.getenv("SIMPLE_RAG_CONDITIONS_MIN_GAP_OVER_ACTIONS", "0.03"))
ACTIONS_MAX_ABS_GAP = float(os.getenv("SIMPLE_RAG_ACTIONS_MAX_ABS_GAP", "0.05"))
STATIC_MAX_ABS_GAP = float(os.getenv("SIMPLE_RAG_STATIC_MAX_ABS_GAP", "0.05"))
STATIC_MIN_GAP_OVER_ACTIONS = float(os.getenv("SIMPLE_RAG_STATIC_MIN_GAP_OVER_ACTIONS", "0.05"))

# Always-included blocks (kept in sync with rag/assembler.py)
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


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )


def _embed_texts(oai: OpenAI, texts: List[str]) -> List[List[float]]:
    resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split())


def _dedupe_by_text(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def _core_blocks() -> List[Dict[str, Any]]:
    return [
        ch for ch in chunk_data
        if ch.get("role") == "static"
        and (ch.get("doc_type") == "CORE" or ch.get("topic") in {"core_intro", "intro", "core"})
    ]


def _is_always_block(ch: Dict[str, Any]) -> bool:
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


def _always_blocks() -> List[Dict[str, Any]]:
    blocks = [ch for ch in chunk_data if _is_always_block(ch)]
    return _dedupe_by_text(blocks)


def _is_conditions_topic(topic: str) -> bool:
    t = (topic or "").lower().strip()
    return t == "conditions" or t.startswith("conditions.") or t.startswith("conditions_")


def _conditions_blocks() -> List[Dict[str, Any]]:
    blocks = [ch for ch in chunk_data if _is_conditions_topic(str(ch.get("topic", "")))]
    return _dedupe_by_text(blocks)


def _is_loops_topic(topic: str) -> bool:
    t = (topic or "").lower().strip()
    return t == "loops" or t.startswith("loops.") or t.startswith("loops_") or t == "flow_formatting"


def _loops_blocks() -> List[Dict[str, Any]]:
    blocks = [ch for ch in chunk_data if _is_loops_topic(str(ch.get("topic", "")))]
    return _dedupe_by_text(blocks)


def _retrieve_top_chunks(query: str, top_k: int) -> List[Dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    client = _get_client()
    col = client.get_collection(name=COLLECTION_NAME)

    qvec = _embed_texts(oai, [query])[0]

    res = col.query(
        query_embeddings=[qvec],
        n_results=top_k,
        include=["distances", "metadatas"],
    )

    metas = (res.get("metadatas") or [[]])[0] or []
    dists = (res.get("distances") or [[]])[0] or []

    # Map retrieved metadatas back to full chunk text
    # Use (doc_type, topic, role, priority) to match the original chunk
    key_map: Dict[Tuple[str, str, str, int], Dict[str, Any]] = {}
    for ch in chunk_data:
        key = (
            str(ch.get("doc_type") or ""),
            str(ch.get("topic") or ""),
            str(ch.get("role") or ""),
            int(ch.get("priority", 0)),
        )
        key_map[key] = ch

    out: List[Dict[str, Any]] = []
    for meta, dist in zip(metas, dists):
        if not meta:
            continue
        key = (
            str(meta.get("doc_type") or ""),
            str(meta.get("topic") or ""),
            str(meta.get("role") or ""),
            int(meta.get("priority", 0) or 0),
        )
        ch = key_map.get(key)
        if ch:
            out.append(
                {
                    "chunk": ch,
                    "distance": float(dist) if dist is not None else None,
                    "meta": meta,
                }
            )

    return out


def _append_conditions_enforcement(prompt: str) -> str:
    return (
        prompt
        + """

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

3) Do NOT place any EVNT_* in ## Steps when Conditions are required.

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
    )


def _append_loops_enforcement(prompt: str) -> str:
    return (
        prompt
        + """

---
LOOPS ENFORCEMENT (HARD RULES)

The router selected the "loops" topic, so repetition is REQUIRED.

You MUST:
1) Include a ## Loops section.
   - If ## Loops is missing, the output is invalid.
2) Express the repetition count explicitly:
   - If the query says "N times" or "repeat N", the loop MUST include count: N.
3) Format inside ## Loops with NO numbered lines:
   - Use ONLY bullet format:
     - EVNT_LOOP_FOR (count: N)
       ↳ INSIDE LOOP: <EVNT_* ...>
4) NEVER place EVNT_LOOP_* or INSIDE LOOP lines inside ## Steps.
   - If any EVNT_LOOP_* appears outside ## Loops, the output is invalid.
5) DO NOT repeat the looped action in ## Steps.
6) If there are no top-level steps outside loops, OMIT the ## Steps section entirely.
7) Do NOT add "Loop End" or any loop closing step.
8) Output must contain exactly one ## Loops section.

If you violate any rule above, your output is invalid.
"""
    )


def build_prompt(user_query: str, top_k: int = TOP_K) -> str:
    parts: List[str] = []

    core = _core_blocks()
    core = _dedupe_by_text(core)

    always = _always_blocks()
    always = _dedupe_by_text(always)

    retrieved = _retrieve_top_chunks(user_query, top_k=top_k)
    retrieved_chunks = [r["chunk"] for r in retrieved]
    retrieved_chunks = _dedupe_by_text(retrieved_chunks)

    # Cap retrieved blocks to avoid huge prompts
    retrieved_chunks = retrieved_chunks[:MAX_BLOCKS]

    # Remove retrieved blocks that are already included in always blocks
    always_hashes = {
        hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest()
        for ch in always
    }
    retrieved_chunks = [
        ch for ch in retrieved_chunks
        if hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest() not in always_hashes
    ]

    for ch in core:
        parts.append(ch["text"].strip())

    for ch in always:
        parts.append(ch["text"].strip())

    for ch in retrieved_chunks:
        parts.append(ch["text"].strip())

    # Use router-role hits and distance gap to decide conditions enforcement
    router_hits = [
        r for r in retrieved
        if (r.get("meta") or {}).get("role") == "router" and r.get("distance") is not None
    ]
    router_hits.sort(key=lambda r: r.get("distance", 1e9))
    conditions_triggered = False
    if router_hits:
        top_dist = router_hits[0].get("distance", 1e9)
        conditions_dist = None
        actions_dist = None
        for r in router_hits:
            topic = str((r.get("meta") or {}).get("topic", "")).lower()
            if _is_conditions_topic(topic) and conditions_dist is None:
                conditions_dist = r.get("distance", 1e9)
            if topic == "actions_builtin_filtering" and actions_dist is None:
                actions_dist = r.get("distance", 1e9)

        if conditions_dist is not None and (conditions_dist - top_dist) <= CONDITIONS_MAX_ABS_GAP:
            if actions_dist is None or (conditions_dist + CONDITIONS_MIN_GAP_OVER_ACTIONS) < actions_dist:
                conditions_triggered = True

    # Notification-only guard: when top router topic is notifications_intent
    # and no action routing topics are present.
    router_topics = [str((r.get("meta") or {}).get("topic", "")).lower() for r in router_hits]
    top_router_topic = router_topics[0] if router_topics else ""
    top_dist = router_hits[0].get("distance", 1e9) if router_hits else 1e9
    has_action_router_close = False
    for r in router_hits:
        topic = str((r.get("meta") or {}).get("topic", "")).lower()
        if topic == "actions_builtin_filtering":
            if (r.get("distance", 1e9) - top_dist) <= ACTIONS_MAX_ABS_GAP:
                has_action_router_close = True
            break
    notification_only = (top_router_topic == "notifications_intent") and not has_action_router_close

    # Static vs dynamic guard: prefer static only if it clearly beats actions router
    static_required = False
    static_dist = None
    actions_dist = None
    for r in router_hits:
        topic = str((r.get("meta") or {}).get("topic", "")).lower()
        if topic == "static_vs_dynamic":
            static_dist = r.get("distance", 1e9)
        if topic == "actions_builtin_filtering":
            actions_dist = r.get("distance", 1e9)

    if static_dist is not None:
        if (static_dist - top_dist) <= STATIC_MAX_ABS_GAP:
            if actions_dist is None or (actions_dist - static_dist) > STATIC_MIN_GAP_OVER_ACTIONS:
                static_required = True

    # If query explicitly mentions role/department, force static
    ql = user_query.lower()
    if (" role " in f" {ql} ") or (" department " in f" {ql} "):
        static_required = True

    # Use any retrieved topic (router/support) to decide loops enforcement
    retrieved_topics = {
        str((r.get("meta") or {}).get("topic", "")).lower()
        for r in retrieved
        if r.get("meta")
    }
    loops_triggered = False
    loops_hits = [
        r for r in retrieved
        if r.get("meta")
        and _is_loops_topic(str((r.get("meta") or {}).get("topic", "")).lower())
        and r.get("distance") is not None
    ]
    if loops_hits:
        best_dist = min(r.get("distance", 1e9) for r in retrieved if r.get("distance") is not None)
        best_loops = min(r.get("distance", 1e9) for r in loops_hits)
        loops_triggered = (best_loops - best_dist) <= LOOPS_MAX_ABS_GAP

    if conditions_triggered:
        condition_blocks = _conditions_blocks()
        # Avoid duplicates against already included content
        existing_hashes = {
            hashlib.sha1(_norm_text(p).encode("utf-8")).hexdigest()
            for p in parts
            if p
        }
        for ch in condition_blocks:
            h = hashlib.sha1(_norm_text(ch.get("text", "")).encode("utf-8")).hexdigest()
            if h in existing_hashes:
                continue
            existing_hashes.add(h)
            parts.append(ch["text"].strip())

    if notification_only:
        parts.append("META.NOTIFICATION_ONLY\n- Only EVNT_NOTI_* steps are allowed. Do NOT add EVNT_RCRD_* or EVNT_FLTR_*.\n")
        # Notification-only requests should not trigger conditions enforcement.
        conditions_triggered = False
        # If notification-only without explicit branching, avoid conditions enforcement.
    if static_required:
        parts.append("META.STATIC_ONLY\n- Use ONLY _STC events for static dimensions (roles/departments). Do NOT use dynamic EVNT_RCRD_*.\n")
        # Static-only requests should not trigger conditions enforcement.
        conditions_triggered = False

    # Loop-only guard: if query implies a loop, avoid conditions enforcement
    ql = user_query.lower()
    loop_only = any(k in ql for k in ["repeat", "times", "loop", "while", "do while", "at least once"])
    if loop_only:
        parts.append("META.LOOP_ONLY\n- Use ONLY loop structures. Do NOT add Conditions for loop-only requests.\n")

    parts.append("USER.QUERY\n" + user_query.strip())

    final_prompt = "\n\n---\n\n".join([p for p in parts if p])

    # Add enforcement blocks when retrieved topics indicate conditions/loops
    # Put loop enforcement at the top of the prompt for higher salience.
    if loops_triggered:
        loops_blocks = _loops_blocks()
        if loops_blocks:
            extra = "\n\n---\n\n".join([b.get("text", "").strip() for b in loops_blocks if b.get("text")])
            if extra:
                final_prompt = extra + "\n\n---\n\n" + final_prompt
        final_prompt = _append_loops_enforcement(final_prompt) + "\n\n---\n\n" + final_prompt
    if conditions_triggered:
        final_prompt = _append_conditions_enforcement(final_prompt)

    return final_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple prompt assembler (data-only retrieval)")
    parser.add_argument("--query", type=str, required=True, help="User query to build a prompt for")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Number of chunks to retrieve")
    args = parser.parse_args()

    prompt = build_prompt(args.query, top_k=args.top_k)
    print(prompt)


if __name__ == "__main__":
    main()
