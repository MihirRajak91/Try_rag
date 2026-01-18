# rag/support_expander.py
from typing import Dict, List, Set, Tuple
from rag.registry import ALL_CHUNKS

ALWAYS_INCLUDE_TOPICS = {"planner_policy"}  # keep tiny; do NOT add "conditions" here


def _key(ch: Dict) -> Tuple:
    return (ch.get("doc_type"), ch.get("topic"), ch.get("role"), int(ch.get("priority", 0)))


def expand_support(allowed_topics: List[str]) -> List[Dict]:
    allowed: Set[str] = set(allowed_topics)

    # Only expand topic families if the parent topic is selected
    existing_topics = {c.get("topic") for c in ALL_CHUNKS}

    if "conditions" in allowed:
        for t in ("cond_bin", "cond_seq", "cond_dom"):
            if t in existing_topics:
                allowed.add(t)

    if "loops" in allowed and "flow_formatting" in existing_topics:
        allowed.add("flow_formatting")

    allowed |= ALWAYS_INCLUDE_TOPICS

    picked = {}
    for ch in ALL_CHUNKS:
        topic = ch.get("topic")
        role = ch.get("role")
        if not topic or role not in {"router", "support"}:
            continue

        # IMPORTANT: only include chunks whose topic is allowed
        if topic in allowed:
            # Optional: do not auto-include CATALOG unless explicitly selected
            if ch.get("doc_type") == "CATALOG" and topic not in set(allowed_topics):
                continue
            picked[_key(ch)] = ch

    return list(picked.values())
