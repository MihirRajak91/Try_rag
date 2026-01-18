# rag/assembler.py
from typing import Dict, List

from rag.registry import ALL_CHUNKS
from rag.router import route_topics
from rag.support_expander import expand_support
import hashlib



def _sort_by_priority_desc(chunks: List[Dict]) -> List[Dict]:
    return sorted(chunks, key=lambda c: int(c.get("priority", 0)), reverse=True)


def assemble_prompt(user_query: str, debug: bool = False) -> str:
    # 1) CORE intro (static always)
    core_blocks = [
        ch for ch in ALL_CHUNKS
        if ch.get("role") == "static" and (
            ch.get("doc_type") == "CORE" or ch.get("topic") in {"core_intro", "intro", "core"}
        )
    ]

    core_blocks = _sort_by_priority_desc(core_blocks)

    # 2) Router topics
    allowed_topics = route_topics(user_query, debug=debug)

    # 3) Expand support
    selected_blocks = expand_support(allowed_topics)

    router_blocks = [ch for ch in selected_blocks if ch.get("role") == "router"]
    support_blocks = [ch for ch in selected_blocks if ch.get("role") == "support"]



    router_blocks = _dedupe_by_text(_sort_by_priority_desc(router_blocks))
    support_blocks = _dedupe_by_text(_sort_by_priority_desc(support_blocks))

    # cross-dedupe: don't include support blocks that repeat router blocks
    router_hashes = {hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() for ch in router_blocks}
    support_blocks = [
        ch for ch in support_blocks
        if hashlib.sha1(ch["text"].strip().encode("utf-8")).hexdigest() not in router_hashes
    ]



    # 4) Build prompt in strict order
    parts: List[str] = []

    for ch in core_blocks:
        parts.append(ch["text"].strip())

    # Router-selected topic blocks
    for ch in router_blocks:
        parts.append(ch["text"].strip())

    # Support blocks (policy, formatting, catalogs)
    for ch in support_blocks:
        parts.append(ch["text"].strip())

    # User query at the end
    parts.append("USER.QUERY\n" + user_query.strip())

    final_prompt = "\n\n---\n\n".join([p for p in parts if p])

    if debug:
        topics_line = ", ".join(allowed_topics) if allowed_topics else "(none)"
        final_prompt = (
            f"[debug] allowed_topics: {topics_line}\n\n"
            + final_prompt
        )

    return final_prompt

def _dedupe_by_text(chunks):
    seen = set()
    out = []
    for ch in chunks:
        txt = ch["text"].strip()
        h = hashlib.sha1(txt.encode("utf-8")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        out.append(ch)
    return out





def main():
    q = input("Enter query: ").strip()
    if not q:
        print("Empty query.")
        return
    prompt = assemble_prompt(q, debug=True)
    print("\n=== FINAL PROMPT ===\n")
    print(prompt)


if __name__ == "__main__":
    main()
