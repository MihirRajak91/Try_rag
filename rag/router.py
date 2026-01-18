import os
import json
import math
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
EMBED_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", os.getenv("EMBED_MODEL", "text-embedding-3-small"))

TOP_K = int(os.getenv("ROUTER_TOP_K", "12"))          # retrieve this many candidates
TOP_ROUTER = int(os.getenv("TOP_ROUTER", "8"))        # only consider this many router hits

# Thresholds for multi-topic selection (based on centroid distances)
ROUTER_MAX_ABS_GAP = float(os.getenv("ROUTER_MAX_ABS_GAP", "0.28"))
ROUTER_MAX_REL_GAP = float(os.getenv("ROUTER_MAX_REL_GAP", "1.35"))
ROUTER_MIN_GAP_TO_ALLOW_MULTI = float(os.getenv("ROUTER_MIN_GAP_TO_ALLOW_MULTI", "0.08"))

MIN_GROUP_SIZE = int(os.getenv("MIN_GROUP_SIZE", "1"))
PRIORITY_EPSILON = float(os.getenv("PRIORITY_EPSILON", "0.01"))

MAX_ALLOWED_TOPICS = int(os.getenv("MAX_ALLOWED_TOPICS", "2"))

STOP_EARLY_TOPICS = ["user_mgmt", "static_vs_dynamic"]
DISALLOWED_OUTPUT_TOPICS = {"router_disambiguation"}

CENTROIDS_PATH = os.path.join(CHROMA_DIR, "topic_centroids.json")


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
    # 1 - cosine similarity
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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    col = _get_collection()
    centroids = _load_centroids()

    qvec = _embed_query(oai, query)

    # Retrieve router chunks
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

    # Take TOP_ROUTER router hits
    cands = sorted(cands, key=lambda x: x.distance)[:TOP_ROUTER]

    # Group by (doc_type, topic, role) and take best per group
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
                "best_dist": best_item.distance,   # from Chroma (NN signal)
                "size": len(items),
            }
        )

    group_summaries = [g for g in group_summaries if g["size"] >= MIN_GROUP_SIZE]
    if not group_summaries:
        return []

    # Sort by Chroma best distance (for display / fallback)
    group_summaries.sort(key=lambda g: g["best_dist"])

    # Priority epsilon tie-break for display ordering
    for i in range(len(group_summaries) - 1):
        a = group_summaries[i]
        b = group_summaries[i + 1]
        if abs(a["best_dist"] - b["best_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
            group_summaries[i], group_summaries[i + 1] = b, a

    # ---- Centroid-based selection (no keywords) ----
    # Only consider topics present in retrieved router hits
    topics_in_hits = [g["topic"] for g in group_summaries if g.get("topic")]
    topics_in_hits = [t for t in topics_in_hits if t not in DISALLOWED_OUTPUT_TOPICS]

    # If centroid file missing or topic missing in centroids, fallback to NN winner
    if centroids:
        scored = []
        for t in topics_in_hits:
            cvec = centroids.get(t)
            if not cvec:
                continue
            cd = _cosine_distance(qvec, cvec)
            # Keep priority for tie-break only
            pr = next((g["priority"] for g in group_summaries if g.get("topic") == t), 0)
            scored.append({"topic": t, "centroid_dist": cd, "priority": pr})

        if scored:
            scored.sort(key=lambda x: x["centroid_dist"])
            # priority epsilon tie-break on centroid distances
            for i in range(len(scored) - 1):
                a = scored[i]
                b = scored[i + 1]
                if abs(a["centroid_dist"] - b["centroid_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
                    scored[i], scored[i + 1] = b, a

            winner = scored[0]

            # Stop-early topics must win by a margin, else prefer runner-up
            if winner["topic"] in STOP_EARLY_TOPICS and len(scored) > 1:
                runner_up = scored[1]
                margin = runner_up["centroid_dist"] - winner["centroid_dist"]
                min_margin = float(os.getenv("STOP_EARLY_MIN_MARGIN", "0.03"))
                if margin < min_margin:
                    winner = runner_up

            allowed_topics = [winner["topic"]]


            # Stop-early topics should not allow multi-topic expansion at all
            #if winner["topic"] in STOP_EARLY_TOPICS:
            #    # (still allow disallowed filtering later)
            #    pass
            #else:
                # allow multi-topic based on centroid distance gaps
                #for s in scored[1:]:
                #    abs_gap = s["centroid_dist"] - winner["centroid_dist"]
                #    rel_gap = s["centroid_dist"] / max(winner["centroid_dist"], 1e-9)

                #    if abs_gap <= ROUTER_MAX_ABS_GAP and rel_gap <= ROUTER_MAX_REL_GAP:
                #        if abs_gap >= ROUTER_MIN_GAP_TO_ALLOW_MULTI:
                #            allowed_topics.append(s["topic"])

                #    if len(allowed_topics) >= MAX_ALLOWED_TOPICS:
                #        break

        else:
            # centroid file exists but none of the hit topics have centroids
            winner_topic = topics_in_hits[0] if topics_in_hits else None
            allowed_topics = [winner_topic] if winner_topic else []

    else:
        # no centroid file -> fallback to NN winner
        winner_topic = topics_in_hits[0] if topics_in_hits else None
        allowed_topics = [winner_topic] if winner_topic else []

    # Stop-early topics should never appear as secondary suggestions
    winner_topic = allowed_topics[0] if allowed_topics else None
    if winner_topic != "user_mgmt":
        allowed_topics = [t for t in allowed_topics if t != "user_mgmt"]
    if winner_topic != "static_vs_dynamic":
        allowed_topics = [t for t in allowed_topics if t != "static_vs_dynamic"]

    # Final cleanup
    allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
    allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]

    if debug:
        print(f"[router] query='{query}'")
        print(f"[router] router_hits={len(cands)} groups={len(group_summaries)}")
        print("[router] group ranking (best_dist, topic, priority):")
        for g in group_summaries:
            print(f"  - {g['best_dist']:.4f}  {g['topic']}  pr={g['priority']} size={g['size']}")

        if centroids:
            # show centroid distances for transparency (only for topics we scored)
            scored_debug = []
            for t in topics_in_hits:
                cvec = centroids.get(t)
                if cvec:
                    cd = _cosine_distance(qvec, cvec)
                    pr = next((g["priority"] for g in group_summaries if g.get("topic") == t), 0)
                    scored_debug.append((cd, t, pr))
            scored_debug.sort(key=lambda x: x[0])

            if scored_debug:
                print("[router] centroid ranking (centroid_dist, topic, priority):")
                for cd, t, pr in scored_debug:
                    print(f"  - {cd:.4f}  {t}  pr={pr}")

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
