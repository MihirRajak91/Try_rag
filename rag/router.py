import os
import json
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI

load_dotenv()

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", os.getenv("CHROMA_DIR", ".chroma"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_chunks_v1")
EMBED_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL",
    os.getenv("EMBED_MODEL", "text-embedding-3-small"),
)

TOP_K = int(os.getenv("ROUTER_TOP_K", "12"))          # retrieve this many candidates
TOP_ROUTER = int(os.getenv("TOP_ROUTER", "8"))        # only consider this many router hits

# Thresholds for multi-topic selection (centroid distances)
ROUTER_MAX_ABS_GAP = float(os.getenv("ROUTER_MAX_ABS_GAP", "0.28"))
ROUTER_MAX_REL_GAP = float(os.getenv("ROUTER_MAX_REL_GAP", "1.35"))

MIN_GROUP_SIZE = int(os.getenv("MIN_GROUP_SIZE", "1"))
PRIORITY_EPSILON = float(os.getenv("PRIORITY_EPSILON", "0.01"))

MAX_ALLOWED_TOPICS = int(os.getenv("MAX_ALLOWED_TOPICS", "2"))

STOP_EARLY_TOPICS = ["user_mgmt", "static_vs_dynamic"]
DISALLOWED_OUTPUT_TOPICS = {"router_disambiguation"}

# Secondary should be included ONLY when the query is truly ambiguous
SECONDARY_AMBIGUITY_ABS_MAX = float(os.getenv("SECONDARY_AMBIGUITY_ABS_MAX", "0.08"))
SECONDARY_AMBIGUITY_REL_MAX = float(os.getenv("SECONDARY_AMBIGUITY_REL_MAX", "1.10"))


CENTROIDS_PATH = os.path.join(CHROMA_DIR, "topic_centroids.json")

# -------------------------------------------------------------------
# Hard precedence gates (deterministic; run before embeddings)
# -------------------------------------------------------------------
STATIC_KEYWORDS = {
    "role", "roles",
    "department", "departments",
}

ACTION_VERBS = {
    "create", "add",
    "update", "modify",
    "delete", "remove",
    "duplicate", "clone",
    "restore", "recover",
}

RECORD_HINTS = {
    "record", "records",
    "entity", "window",
    "row", "rows",
    "entry", "entries",
}

TOPIC_ALIASES = {
    "data_extraction": "data_retrieval_filtering",
    "data_extraction.fltr": "data_retrieval_filtering",
    "data_extraction.jmes": "data_retrieval_filtering",
    "data_extraction.rcrd_info": "data_retrieval_filtering",
}

USER_KEYWORDS = {
    "user", "users",
    "permission", "permissions",
    "access",
}

USER_ACTION_HINTS = {
    "add", "create",
    "update", "modify",
    "deactivate", "activate",
    "assign", "grant", "revoke",
    "extend",
}

USER_ROLE_PHRASES = {
    "assign role",
    "role assignment",
    "assign roles",
}

# -------------------------------------------------------------------
# Pair preferences (NO KEYWORDS): winner -> preferred secondary topics
# This is deterministic and based only on the router topic IDs.
# -------------------------------------------------------------------
PAIR_PREFERENCES = {
    # If winner is notifications, conditions is the most useful “secondary”
    "notifications_intent": {"conditions"},
}


# ----------------------------
# Router Output Contract
# ----------------------------
@dataclass(frozen=True)
class RoutingResult:
    topics: Tuple[str, ...]      # ordered: winner first, then secondary
    winner: str                  # topics[0] if any, else ""
    secondary: Tuple[str, ...]   # topics[1:]


def _tokens(q: str) -> set:
    return set(re.findall(r"[a-z]+", (q or "").lower()))


def _forced_topic_gate(query: str) -> Optional[str]:
    """
    Deterministic precedence:
    0) user_mgmt wins if the main action is on users (create/update/deactivate/assign/extend)
    1) static_vs_dynamic wins if static keyword present (role/department etc.) AND it's NOT user_mgmt intent
    2) actions_builtin_filtering wins if CRUD verb + record hint present
    """
    q = (query or "").lower()
    t = _tokens(q)

    # 0) USER MGMT gate ALWAYS wins for user actions (even if 'role' appears)
    if (t & USER_KEYWORDS) and ((t & USER_ACTION_HINTS) or any(p in q for p in USER_ROLE_PHRASES)):
        return "user_mgmt"

    # 1) Static gate wins when static entities are mentioned (role/department)
    if t & STATIC_KEYWORDS:
        return "static_vs_dynamic"

    # 2) CRUD gate (requires record hint to avoid catching user_mgmt-like queries)
    if (t & ACTION_VERBS) and (t & RECORD_HINTS):
        return "actions_builtin_filtering"

    return None


@dataclass
class Candidate:
    chunk_id: str
    distance: float
    meta: Dict


def _embed_query(oai: OpenAI, text: str) -> List[float]:
    resp = oai.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


def _get_collection():
    chroma = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    return chroma.get_collection(name=COLLECTION_NAME)


def _group_key(meta: Dict) -> Tuple[str, str, str]:
    return (meta.get("doc_type"), meta.get("topic"), meta.get("role"))


def _cosine_distance(a: List[float], b: List[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        fx = float(x)
        fy = float(y)
        dot += fx * fy
        na += fx * fx
        nb += fy * fy
    if na <= 0.0 or nb <= 0.0:
        return 1.0
    return 1.0 - (dot / (math.sqrt(na) * math.sqrt(nb)))


def _load_centroids() -> Optional[Dict[str, List[float]]]:
    try:
        with open(CENTROIDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        centroids = data.get("centroids", {})
        if not isinstance(centroids, dict) or not centroids:
            return None
        return centroids
    except Exception:
        return None


def route_topics(query: str, debug: bool = True) -> List[str]:
    # ---- Hard precedence gate (before embeddings + chroma) ----
    forced = _forced_topic_gate(query)
    if forced:
        allowed_topics = [TOPIC_ALIASES.get(forced, forced)]
        if debug:
            print(f"[router] query='{query}'")
            print(f"[router] forced_topic_gate={forced}")
            print(f"[router] allowed_topics={allowed_topics}")
        return allowed_topics

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    col = _get_collection()
    centroids = _load_centroids()

    qvec = _embed_query(oai, query)

    res = col.query(
        query_embeddings=[qvec],
        n_results=TOP_K,
        include=["distances", "metadatas"],
    )

    ids = res.get("ids", [[]])[0]
    dists = res.get("distances", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    cands: List[Candidate] = []
    for cid, dist, meta in zip(ids, dists, metas):
        if (meta or {}).get("role") == "router":
            cands.append(Candidate(chunk_id=cid, distance=float(dist), meta=meta or {}))

    if not cands:
        return []

    cands = sorted(cands, key=lambda x: x.distance)[:TOP_ROUTER]

    groups: Dict[Tuple[str, str, str], List[Candidate]] = {}
    for c in cands:
        groups.setdefault(_group_key(c.meta), []).append(c)

    group_summaries = []
    for gk, items in groups.items():
        best_item = min(items, key=lambda x: x.distance)
        group_summaries.append(
            {
                "gk": gk,
                "topic": best_item.meta.get("topic"),
                "doc_type": best_item.meta.get("doc_type"),
                "role": best_item.meta.get("role"),
                "priority": int(best_item.meta.get("priority", 0)),
                "best_dist": best_item.distance,
                "size": len(items),
            }
        )

    group_summaries = [g for g in group_summaries if g["size"] >= MIN_GROUP_SIZE]
    if not group_summaries:
        return []

    group_summaries.sort(key=lambda g: g["best_dist"])

    for i in range(len(group_summaries) - 1):
        a = group_summaries[i]
        b = group_summaries[i + 1]
        if abs(a["best_dist"] - b["best_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
            group_summaries[i], group_summaries[i + 1] = b, a

    topics_in_hits = [g["topic"] for g in group_summaries if g.get("topic")]
    topics_in_hits = [t for t in topics_in_hits if t not in DISALLOWED_OUTPUT_TOPICS]

    if centroids:
        scored = []
        for t in topics_in_hits:
            cvec = centroids.get(t)
            if not cvec:
                continue
            cd = _cosine_distance(qvec, cvec)
            pr = next((g["priority"] for g in group_summaries if g.get("topic") == t), 0)
            scored.append({"topic": t, "centroid_dist": cd, "priority": pr})

        if scored:
            scored.sort(key=lambda x: x["centroid_dist"])

            # do NOT let stop-early topics jump ahead of non-stop-early topics as runner-up
            for i in range(len(scored) - 1):
                a = scored[i]
                b = scored[i + 1]
                if abs(a["centroid_dist"] - b["centroid_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
                    a_stop = a["topic"] in STOP_EARLY_TOPICS
                    b_stop = b["topic"] in STOP_EARLY_TOPICS
                    if not (b_stop and not a_stop):
                        scored[i], scored[i + 1] = b, a

            winner = scored[0]

            if winner["topic"] in STOP_EARLY_TOPICS and len(scored) > 1:
                runner_up = scored[1]
                margin = runner_up["centroid_dist"] - winner["centroid_dist"]
                min_margin = float(os.getenv("STOP_EARLY_MIN_MARGIN", "0.03"))
                if margin < min_margin:
                    winner = runner_up

            allowed_topics: List[str] = [winner["topic"]]

            # -------------------------------------------------------------------
            # Secondary selection (centroid-only) with ambiguity gate + pair preference
            # -------------------------------------------------------------------
            if winner["topic"] not in STOP_EARLY_TOPICS and MAX_ALLOWED_TOPICS > 1:
                # filter out stop-early candidates
                candidates = [s for s in scored[1:] if s["topic"] not in STOP_EARLY_TOPICS]
                if candidates:
                    # Ambiguity gate: only consider secondary if runner-up is very close
                    runner_up = candidates[0]
                    abs_gap_amb = runner_up["centroid_dist"] - winner["centroid_dist"]
                    rel_gap_amb = runner_up["centroid_dist"] / max(winner["centroid_dist"], 1e-9)

                    if abs_gap_amb <= SECONDARY_AMBIGUITY_ABS_MAX and rel_gap_amb <= SECONDARY_AMBIGUITY_REL_MAX:
                        preferred = PAIR_PREFERENCES.get(winner["topic"], set())

                        # reorder: preferred topics first, then the rest (stable)
                        preferred_candidates = [s for s in candidates if s["topic"] in preferred]
                        other_candidates = [s for s in candidates if s["topic"] not in preferred]
                        ordered = preferred_candidates + other_candidates

                        for s in ordered:
                            abs_gap = s["centroid_dist"] - winner["centroid_dist"]
                            rel_gap = s["centroid_dist"] / max(winner["centroid_dist"], 1e-9)
                            if abs_gap <= ROUTER_MAX_ABS_GAP and rel_gap <= ROUTER_MAX_REL_GAP:
                                allowed_topics.append(s["topic"])
                                break


            allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
            allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]
            allowed_topics = [TOPIC_ALIASES.get(t, t) for t in allowed_topics]

            if debug:
                print(f"[router] query='{query}'")
                print(f"[router] router_hits={len(cands)} groups={len(group_summaries)}")
                print("[router] group ranking (best_dist, topic, priority):")
                for g in group_summaries:
                    print(f"  - {g['best_dist']:.4f}  {g['topic']}  pr={g['priority']} size={g['size']}")
                print("[router] centroid ranking (centroid_dist, topic, priority):")
                for s in scored:
                    print(f"  - {s['centroid_dist']:.4f}  {s['topic']}  pr={s['priority']}")
                print(f"[router] allowed_topics={allowed_topics}")

            return allowed_topics

    winner_topic = topics_in_hits[0] if topics_in_hits else None
    allowed_topics = [winner_topic] if winner_topic else []
    allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
    allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]
    allowed_topics = [TOPIC_ALIASES.get(t, t) for t in allowed_topics]
    return allowed_topics


def route(query: str, debug: bool = True) -> RoutingResult:
    topics = route_topics(query, debug=debug)
    if not topics:
        return RoutingResult(topics=(), winner="", secondary=())
    t = tuple(topics)
    return RoutingResult(
        topics=t,
        winner=t[0],
        secondary=t[1:],
    )


def main():
    query = input("Enter query: ").strip()
    if not query:
        print("Empty query.")
        return
    route_topics(query, debug=True)


if __name__ == "__main__":
    main()
