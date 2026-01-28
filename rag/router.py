# rag/router.py
import os
import json
import math
import time
import logging

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from openai import OpenAI

load_dotenv()
logger = logging.getLogger(__name__)

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", os.getenv("CHROMA_DIR", ".chroma"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_chunks_v1")
EMBED_MODEL = os.getenv(
    "OPENAI_EMBEDDING_MODEL",
    os.getenv("EMBED_MODEL", "text-embedding-3-small"),
)

TOP_K = int(os.getenv("ROUTER_TOP_K", "12"))
TOP_ROUTER = int(os.getenv("TOP_ROUTER", "8"))

ROUTER_MAX_ABS_GAP = float(os.getenv("ROUTER_MAX_ABS_GAP", "0.28"))
ROUTER_MAX_REL_GAP = float(os.getenv("ROUTER_MAX_REL_GAP", "1.35"))

MIN_GROUP_SIZE = int(os.getenv("MIN_GROUP_SIZE", "1"))
PRIORITY_EPSILON = float(os.getenv("PRIORITY_EPSILON", "0.01"))

MAX_ALLOWED_TOPICS = int(os.getenv("MAX_ALLOWED_TOPICS", "2"))

SECONDARY_AMBIGUITY_ABS_MAX = float(os.getenv("SECONDARY_AMBIGUITY_ABS_MAX", "0.08"))
SECONDARY_AMBIGUITY_REL_MAX = float(os.getenv("SECONDARY_AMBIGUITY_REL_MAX", "1.10"))

CENTROIDS_PATH = os.path.join(CHROMA_DIR, "topic_centroids.json")

# --- Safe defaults (do NOT comment these out unless you also remove references) ---
STOP_EARLY_TOPICS = ["user_mgmt", "static_vs_dynamic"]
DISALLOWED_OUTPUT_TOPICS = {"router_disambiguation"}

TOPIC_ALIASES = {
    "data_extraction": "data_retrieval_filtering",
    "data_extraction.fltr": "data_retrieval_filtering",
    "data_extraction.jmes": "data_retrieval_filtering",
    "data_extraction.rcrd_info": "data_retrieval_filtering",
}


class _Timer:
    def __init__(self):
        self.start = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self.start


# ----------------------------
# Router Output Contract
# ----------------------------
@dataclass(frozen=True)
class RoutingResult:
    topics: Tuple[str, ...]
    winner: str
    secondary: Tuple[str, ...]
    timing: Dict[str, float] = field(default_factory=dict)


@dataclass
class Candidate:
    chunk_id: str
    distance: float
    meta: Dict


def _embed_query(oai: OpenAI, text: str) -> Tuple[List[float], float]:
    t = _Timer()
    resp = oai.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding, t.elapsed()


def _get_collection():
    chroma = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    return chroma.get_collection(name=COLLECTION_NAME)


def _group_key(meta: Dict) -> Tuple[str, str, str]:
    doc_type = str(meta.get("doc_type") or "")
    topic = str(meta.get("topic") or "")
    role = str(meta.get("role") or "")
    return (doc_type, topic, role)


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


def _uniq_stable(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def route_topics(query: str, debug: bool = True) -> Tuple[List[str], Dict[str, float]]:
    """
    Embedding-only router:
    - No keyword forced-gates
    - Topics selected by centroid similarity with optional secondary topic
    - Optional 'conditions' overlay is centroid-distance based (no keyword detection)

    IMPORTANT INVARIANT:
    - len(allowed_topics) must never exceed MAX_ALLOWED_TOPICS
    """
    timing: Dict[str, float] = {}
    router_timer = _Timer()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    col = _get_collection()
    centroids = _load_centroids()

    # 1) Embed query
    qvec, embed_s = _embed_query(oai, query)
    timing["embed_s"] = embed_s

    # 2) Get nearest router chunks
    t_chroma = _Timer()
    res = col.query(
        query_embeddings=[qvec],
        n_results=TOP_K,
        include=["distances", "metadatas"],
    )
    timing["chroma_s"] = t_chroma.elapsed()

    ids = (res.get("ids") or [[]])[0] or []
    dists = (res.get("distances") or [[]])[0] or []
    metas = (res.get("metadatas") or [[]])[0] or []

    cands: List[Candidate] = []
    for cid, dist, meta in zip(ids, dists, metas):
        md = meta or {}
        if md.get("role") == "router":
            cands.append(Candidate(chunk_id=str(cid), distance=float(dist), meta=md))

    timing["router_hits"] = float(len(cands))
    if not cands:
        timing["router_total_s"] = router_timer.elapsed()
        return [], timing

    cands = sorted(cands, key=lambda x: x.distance)[:TOP_ROUTER]

    # 3) Group by (doc_type, topic, role) to avoid duplicate hits from same topic/role
    groups: Dict[Tuple[str, str, str], List[Candidate]] = {}
    for c in cands:
        groups.setdefault(_group_key(c.meta), []).append(c)
    timing["groups"] = float(len(groups))

    group_summaries = []
    for gk, items in groups.items():
        best_item = min(items, key=lambda x: x.distance)
        group_summaries.append(
            {
                "gk": gk,
                "topic": str(best_item.meta.get("topic") or ""),
                "doc_type": str(best_item.meta.get("doc_type") or ""),
                "role": str(best_item.meta.get("role") or ""),
                "priority": int(best_item.meta.get("priority", 0)),
                "best_dist": best_item.distance,
                "size": len(items),
            }
        )

    group_summaries = [g for g in group_summaries if g["size"] >= MIN_GROUP_SIZE and g["topic"]]
    if not group_summaries:
        timing["router_total_s"] = router_timer.elapsed()
        return [], timing

    group_summaries.sort(key=lambda g: g["best_dist"])

    # priority tie-break on best_dist ties
    for i in range(len(group_summaries) - 1):
        a = group_summaries[i]
        b = group_summaries[i + 1]
        if abs(a["best_dist"] - b["best_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
            group_summaries[i], group_summaries[i + 1] = b, a

    topics_in_hits = _uniq_stable([g["topic"] for g in group_summaries])
    topics_in_hits = [t for t in topics_in_hits if t not in DISALLOWED_OUTPUT_TOPICS]

    # 4) If no centroids, fall back to best hit topic(s)
    if not centroids:
        allowed = topics_in_hits[:MAX_ALLOWED_TOPICS]
        allowed = [t for t in allowed if t and t not in DISALLOWED_OUTPUT_TOPICS]
        allowed = [TOPIC_ALIASES.get(t, t) for t in allowed]
        timing["centroid_s"] = 0.0
        timing["router_total_s"] = router_timer.elapsed()
        return allowed, timing

    # 5) Score topics by centroid distance
    t_centroids = _Timer()
    scored: List[Dict] = []
    for tpc in topics_in_hits:
        cvec = centroids.get(tpc)
        if not cvec:
            continue
        cd = _cosine_distance(qvec, cvec)
        pr = next((g["priority"] for g in group_summaries if g.get("topic") == tpc), 0)
        scored.append({"topic": tpc, "centroid_dist": cd, "priority": pr})

    if not scored:
        timing["centroid_s"] = t_centroids.elapsed()
        timing["router_total_s"] = router_timer.elapsed()
        return [], timing

    scored.sort(key=lambda x: x["centroid_dist"])

    if debug:
        print("[router] scored_topics:", [(s["topic"], round(s["centroid_dist"], 4)) for s in scored[:8]])

    # priority tie-break on centroid ties (stop-early shouldn’t jump ahead artificially)
    for i in range(len(scored) - 1):
        a = scored[i]
        b = scored[i + 1]
        if abs(a["centroid_dist"] - b["centroid_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
            a_stop = a["topic"] in STOP_EARLY_TOPICS
            b_stop = b["topic"] in STOP_EARLY_TOPICS
            if not (b_stop and not a_stop):
                scored[i], scored[i + 1] = b, a

    winner = scored[0]

    # Optional stop-early margin behavior (distance-based)
    if winner["topic"] in STOP_EARLY_TOPICS and len(scored) > 1:
        runner_up = scored[1]
        margin = runner_up["centroid_dist"] - winner["centroid_dist"]
        min_margin = float(os.getenv("STOP_EARLY_MIN_MARGIN", "0.03"))
        if margin < min_margin:
            winner = runner_up

    allowed_topics: List[str] = [winner["topic"]]

    # 6) Pick ONE secondary topic (distance/ambiguity gated)
    if MAX_ALLOWED_TOPICS > 1 and len(scored) > 1:
        candidates = scored[1:]
        runner_up = candidates[0]

        abs_gap_amb = runner_up["centroid_dist"] - winner["centroid_dist"]
        rel_gap_amb = runner_up["centroid_dist"] / max(winner["centroid_dist"], 1e-9)

        if abs_gap_amb <= SECONDARY_AMBIGUITY_ABS_MAX and rel_gap_amb <= SECONDARY_AMBIGUITY_REL_MAX:
            for s in candidates:
                abs_gap = s["centroid_dist"] - winner["centroid_dist"]
                rel_gap = s["centroid_dist"] / max(winner["centroid_dist"], 1e-9)
                if abs_gap <= ROUTER_MAX_ABS_GAP and rel_gap <= ROUTER_MAX_REL_GAP:
                    allowed_topics.append(s["topic"])
                    break

    # cap action topics
    allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]

    # 7) Optional overlay: add "conditions" only if it’s genuinely close by centroid distance
    cond = next((s for s in scored if s["topic"] == "conditions"), None)
    if cond and winner["topic"] != "conditions" and "conditions" not in allowed_topics:
        abs_gap = cond["centroid_dist"] - winner["centroid_dist"]
        rel_gap = cond["centroid_dist"] / max(winner["centroid_dist"], 1e-9)
        if abs_gap <= SECONDARY_AMBIGUITY_ABS_MAX and rel_gap <= SECONDARY_AMBIGUITY_REL_MAX:
            # RESPECT MAX_ALLOWED_TOPICS:
            # If already at cap, replace the secondary slot with "conditions"
            if len(allowed_topics) >= MAX_ALLOWED_TOPICS:
                if MAX_ALLOWED_TOPICS > 1:
                    allowed_topics[1] = "conditions"
                # else MAX_ALLOWED_TOPICS == 1: keep winner only
            else:
                allowed_topics.append("conditions")

    # Final cleanup
    allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
    allowed_topics = [TOPIC_ALIASES.get(t, t) for t in allowed_topics]

    timing["centroid_s"] = t_centroids.elapsed()
    timing["router_total_s"] = router_timer.elapsed()

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

    return allowed_topics, timing


def route(query: str, debug: bool = True) -> RoutingResult:
    topics, timing = route_topics(query, debug=debug)
    if not topics:
        return RoutingResult(topics=(), winner="", secondary=(), timing=timing)
    t = tuple(topics)
    return RoutingResult(
        topics=t,
        winner=t[0],
        secondary=t[1:],
        timing=timing,
    )


def main():
    query = input("Enter query: ").strip()
    if not query:
        print("Empty query.")
        return
    topics, timing = route_topics(query, debug=True)
    print("topics:", topics)
    print("timing:", timing)


if __name__ == "__main__":
    main()
