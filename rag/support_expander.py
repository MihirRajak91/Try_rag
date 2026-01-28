# rag/support_expander.py
from typing import Dict, List, Set, Tuple
from rag.registry import ALL_CHUNKS

ALWAYS_INCLUDE_TOPICS = {"planner_policy"}  # keep tiny

# Topic families (only used for deterministic boundary gating)
USER_MGMT_FAMILY = {"user_mgmt"}
STATIC_FAMILY = {"static_vs_dynamic"}
CRUD_FAMILY = {"actions_builtin_filtering", "data_retrieval_filtering"}
CONDITIONS_FAMILY = {"conditions", "conditions.bin", "conditions.seq", "conditions.dom"}

LOOPS_FAMILY = {"loops", "flow_formatting"}


def _key(ch: Dict) -> Tuple:
    return (ch.get("doc_type"), ch.get("topic"), ch.get("role"), int(ch.get("priority", 0)))


def expand_support(allowed_topics: List[str], *, winner: str | None = None) -> List[Dict]:
    allowed: Set[str] = set(allowed_topics)

    # Only expand topic families if the parent topic is selected
    existing_topics = {c.get("topic") for c in ALL_CHUNKS}

    # ---- Family expansions (opt-in, deterministic) ----
    if "conditions" in allowed:
        # Include all condition subtopics that exist (more robust than hardcoding)
        for t in existing_topics:
            if isinstance(t, str) and (t.startswith("conditions.") or t.startswith("conditions_")):
                allowed.add(t)

    if "loops" in allowed and "flow_formatting" in existing_topics:
        allowed.add("flow_formatting")

    # ---- Boundary gates (defensive, future-proof) ----
    # If user_mgmt is present, it dominates support expansion: keep it clean.
    # if winner == "user_mgmt":
    #     allowed = (allowed & USER_MGMT_FAMILY) | ALWAYS_INCLUDE_TOPICS

    # If static_vs_dynamic is present (and user_mgmt isn't), prevent CRUD bleed.
    if "static_vs_dynamic" in allowed:
        allowed = allowed - CRUD_FAMILY - USER_MGMT_FAMILY

    # If actions_builtin_filtering is present, prevent static/user_mgmt bleed.
    if "actions_builtin_filtering" in allowed:
        allowed = allowed - STATIC_FAMILY - USER_MGMT_FAMILY

    if "actions_builtin_filtering" in allowed:
        allowed.discard("user_mgmt")

    # Always-include topics last (so they survive gating)
    allowed |= ALWAYS_INCLUDE_TOPICS

    picked = {}
    base_allowed = set(allowed_topics)  # explicit topics user/router picked

    for ch in ALL_CHUNKS:
        topic = ch.get("topic")
        role = ch.get("role")
        if not topic or role not in {"router", "support"}:
            continue

        # Only include chunks whose topic is allowed
        if topic in allowed:
            # Do not auto-include CATALOG unless explicitly selected as a base topic
            if str(ch.get("doc_type", "")).upper() == "CATALOG" and topic not in base_allowed:
                continue
            picked[_key(ch)] = ch

    return list(picked.values())
