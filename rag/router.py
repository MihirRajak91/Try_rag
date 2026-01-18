# rag/router.py
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI

load_dotenv()

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_DIR", ".chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "workflow_rules_v1")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

TOP_K = int(os.getenv("ROUTER_TOP_K", "12"))          # retrieve this many candidates
TOP_ROUTER = int(os.getenv("TOP_ROUTER", "8"))        # only consider this many router hits

# Thresholds (tune later with tests)
ROUTER_MAX_ABS_GAP = float(os.getenv("ROUTER_MAX_ABS_GAP", "0.28"))
ROUTER_MAX_REL_GAP = float(os.getenv("ROUTER_MAX_REL_GAP", "1.35"))
ROUTER_MIN_GAP_TO_ALLOW_MULTI = float(os.getenv("ROUTER_MIN_GAP_TO_ALLOW_MULTI", "0.08"))

MIN_GROUP_SIZE = int(os.getenv("MIN_GROUP_SIZE", "1"))  # keep 1 for now (you only have 1 router chunk/topic)
PRIORITY_EPSILON = float(os.getenv("PRIORITY_EPSILON", "0.03"))  # if distances within eps, prefer higher priority

MAX_ALLOWED_TOPICS = int(os.getenv("MAX_ALLOWED_TOPICS", "2"))

STOP_EARLY_TOPICS = ["user_mgmt", "static_vs_dynamic"]


@dataclass
class Candidate:
    chunk_id: str
    distance: float
    meta: Dict

RETRIEVAL_KEYWORDS = {
    "get", "fetch", "retrieve", "list", "show", "view", "find", "search", "display"
}
ACTION_KEYWORDS = {
    "create", "add", "update", "modify", "delete", "remove", "duplicate", "restore"
}

STOP_EARLY_GATES = ["user_mgmt", "static_vs_dynamic"]


def _is_retrieval_query(q: str) -> bool:
    ql = q.strip().lower()
    # Strong retrieval patterns
    if ql.startswith(("get ", "list ", "show ", "fetch ", "retrieve ", "find ")):
        return True
    if "get records" in ql or "list records" in ql or "retrieve records" in ql:
        return True
    return False



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


def route_topics(query: str, debug: bool = True) -> List[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    col = _get_collection()

    qvec = _embed_query(oai, query)

    res = col.query(
        query_embeddings=[qvec],
        n_results=TOP_K,
        include=["distances", "metadatas"],
    )

    ids = res.get("ids", [[]])[0]
    dists = res.get("distances", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    # Build candidate list and filter router-only
    cands = []
    for cid, dist, meta in zip(ids, dists, metas):
        if (meta or {}).get("role") == "router":
            cands.append(Candidate(chunk_id=cid, distance=float(dist), meta=meta))

    if not cands:
        # Fallback: no router matches (shouldn't happen once you have router chunks)
        return []

    # Take TOP_ROUTER router hits
    cands = sorted(cands, key=lambda x: x.distance)[:TOP_ROUTER]

    # Group by (doc_type, topic, role) and take best per group
    groups: Dict[Tuple[str, str, str], List[Candidate]] = {}
    for c in cands:
        groups.setdefault(_group_key(c.meta), []).append(c)

    group_summaries = []
    for gk, items in groups.items():
        best = min(items, key=lambda x: x.distance)
        # group distance = best distance for now
        group_summaries.append(
            {
                "gk": gk,
                "topic": best.meta.get("topic"),
                "doc_type": best.meta.get("doc_type"),
                "role": best.meta.get("role"),
                "priority": int(best.meta.get("priority", 0)),
                "best_dist": best.distance,
                "size": len(items),
            }
        )

    # Apply MIN_GROUP_SIZE
    group_summaries = [g for g in group_summaries if g["size"] >= MIN_GROUP_SIZE]
    if not group_summaries:
        return []

    # Sort by best distance (then priority as tie-breaker within epsilon)
    group_summaries.sort(key=lambda g: g["best_dist"])

    # Priority epsilon tie-break: if near-equal, prefer higher priority
    # We do one pass bubble-like adjustment for top few.
    for i in range(len(group_summaries) - 1):
        a = group_summaries[i]
        b = group_summaries[i + 1]
        if abs(a["best_dist"] - b["best_dist"]) <= PRIORITY_EPSILON:
            if b["priority"] > a["priority"]:
                group_summaries[i], group_summaries[i + 1] = b, a

    best = group_summaries[0]
    allowed = [best]
    allowed = allowed[:MAX_ALLOWED_TOPICS]


    # Decide if we allow multi-topic
    for g in group_summaries[1:]:
        abs_gap = g["best_dist"] - best["best_dist"]
        rel_gap = g["best_dist"] / max(best["best_dist"], 1e-9)

        # allow additional topic if it's close enough
        if abs_gap <= ROUTER_MAX_ABS_GAP and rel_gap <= ROUTER_MAX_REL_GAP:
            # but require enough separation from best to justify multi-topic
            # (prevents always adding 2nd topic when everything is extremely close)
            if abs_gap >= ROUTER_MIN_GAP_TO_ALLOW_MULTI:
                allowed.append(g)

    allowed_topics = [g["topic"] for g in allowed if g["topic"]]

    # Stop-early gates
# Stop-early gates: ONLY if the WINNER is a stop-early topic
    winner_topic = best.get("topic")
    if winner_topic in STOP_EARLY_TOPICS:
        allowed_topics = [winner_topic]

    if debug:
        print(f"[router] query='{query}'")
        print(f"[router] router_hits={len(cands)} groups={len(group_summaries)}")
        print("[router] group ranking (best_dist, topic, priority):")
        for g in group_summaries:
            print(f"  - {g['best_dist']:.4f}  {g['topic']}  pr={g['priority']} size={g['size']}")
        allowed_topics = [g["topic"] for g in allowed if g["topic"]]

        # stop-early gates (you already have this)
        # Stop-early gates: ONLY if the WINNER is a stop-early topic
        winner_topic = best.get("topic")
        if winner_topic in STOP_EARLY_TOPICS:
            allowed_topics = [winner_topic]


        # ---- Hard gate: retrieval must not route to action CRUD topics
        if _is_retrieval_query(query):
            allowed_topics = [t for t in allowed_topics if t != "actions_builtin_filtering"]
            if not allowed_topics:
                allowed_topics = ["data_retrieval_filtering"]

        if debug:
            print(f"[router] allowed_topics={allowed_topics}")

        return allowed_topics





def main():
    query = input("Enter query: ").strip()
    if not query:
        print("Empty query.")
        return
    route_topics(query, debug=True)


if __name__ == "__main__":
    main()
