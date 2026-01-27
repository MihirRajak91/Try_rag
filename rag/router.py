import os
import json
import math
import re
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

STOP_EARLY_TOPICS = ["user_mgmt", "static_vs_dynamic"]
DISALLOWED_OUTPUT_TOPICS = {"router_disambiguation"}

SECONDARY_AMBIGUITY_ABS_MAX = float(os.getenv("SECONDARY_AMBIGUITY_ABS_MAX", "0.08"))
SECONDARY_AMBIGUITY_REL_MAX = float(os.getenv("SECONDARY_AMBIGUITY_REL_MAX", "1.10"))

CENTROIDS_PATH = os.path.join(CHROMA_DIR, "topic_centroids.json")

# -------------------------------------------------------------------
# Hard precedence gates (deterministic; run before embeddings)
# -------------------------------------------------------------------
STATIC_KEYWORDS = {"role", "roles", "department", "departments"}

ACTION_VERBS = {"create", "add", "update", "modify", "delete", "remove", "duplicate", "clone", "restore", "recover"}

RECORD_HINTS = {"record", "records", "entity", "window", "row", "rows", "entry", "entries"}

TOPIC_ALIASES = {
    "data_extraction": "data_retrieval_filtering",
    "data_extraction.fltr": "data_retrieval_filtering",
    "data_extraction.jmes": "data_retrieval_filtering",
    "data_extraction.rcrd_info": "data_retrieval_filtering",
}

USER_KEYWORDS = {"user", "users", "permission", "permissions", "access"}

USER_ACTION_HINTS = {"add", "create", "update", "modify", "deactivate", "activate", "assign", "grant", "revoke", "extend"}

USER_ROLE_PHRASES = {"assign role", "role assignment", "assign roles"}

# -------------------------------------------------------------------
# Pair preferences (NO KEYWORDS): winner -> preferred secondary topics
# -------------------------------------------------------------------
# PAIR_PREFERENCES = {
#     "notifications_intent": {"conditions"},
# }


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


def _tokens(q: str) -> set:
    return set(re.findall(r"[a-z]+", (q or "").lower()))


def _forced_topic_gate(query: str) -> Optional[str]:
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
    # normalize to strings so grouping doesn't get weird when values are None
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


def _has_condition_language(q: str) -> bool:
    s = (q or "").lower()
    strong = [
        "and check if",
        "and verify if",
        "verify if",
        "check if",
        "if not",
        "else check",
        "fails",
        "first check",
        "if ",
        " when ",
    ]
    if any(k in s for k in strong):
        return True
    return len(re.findall(r"\bif\b", s)) >= 2


def _uniq_stable(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def route_topics(query: str, debug: bool = True) -> Tuple[List[str], Dict[str, float]]:
    timing: Dict[str, float] = {}
    router_timer = _Timer()

    # ---- Hard precedence gate (before embeddings + chroma) ----
    t_gate = _Timer()
    forced = _forced_topic_gate(query)
    timing["forced_gate_s"] = t_gate.elapsed()

    if forced:
        allowed_topics = [TOPIC_ALIASES.get(forced, forced)]
        timing["router_total_s"] = router_timer.elapsed()
        if debug:
            print(f"[router] query='{query}'")
            print(f"[router] forced_topic_gate={forced}")
            print(f"[router] allowed_topics={allowed_topics}")
        return allowed_topics, timing

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    col = _get_collection()
    centroids = _load_centroids()

    qvec, embed_s = _embed_query(oai, query)
    timing["embed_s"] = embed_s

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

    # priority tie-break
    for i in range(len(group_summaries) - 1):
        a = group_summaries[i]
        b = group_summaries[i + 1]
        if abs(a["best_dist"] - b["best_dist"]) <= PRIORITY_EPSILON and b["priority"] > a["priority"]:
            group_summaries[i], group_summaries[i + 1] = b, a

    topics_in_hits = _uniq_stable([g["topic"] for g in group_summaries])
    topics_in_hits = [t for t in topics_in_hits if t not in DISALLOWED_OUTPUT_TOPICS]

    # If we don't have centroids, fall back to best hit topic
    if not centroids:
        winner_topic = topics_in_hits[0] if topics_in_hits else None
        allowed_topics = [winner_topic] if winner_topic else []
        allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
        allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]
        allowed_topics = [TOPIC_ALIASES.get(t, t) for t in allowed_topics]
        timing["router_total_s"] = router_timer.elapsed()
        timing["centroid_s"] = 0.0
        return allowed_topics, timing

    t_centroids = _Timer()

    scored = []
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


    # priority tie-break, but don't let stop-early jump as runner-up
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

    # conditions auto-include (only if it's present in hits)
    if (
        MAX_ALLOWED_TOPICS > 1
        and _has_condition_language(query)
        and winner["topic"] != "conditions"
        and "conditions" in topics_in_hits
        and "conditions" not in allowed_topics
    ):
        allowed_topics.append("conditions")

    # # Secondary selection with ambiguity gate + pair preference
    # if winner["topic"] not in STOP_EARLY_TOPICS and MAX_ALLOWED_TOPICS > 1:
    #     candidates = [s for s in scored[1:] if s["topic"] not in STOP_EARLY_TOPICS]
    #     if candidates:
    #         runner_up = candidates[0]
    #         abs_gap_amb = runner_up["centroid_dist"] - winner["centroid_dist"]
    #         rel_gap_amb = runner_up["centroid_dist"] / max(winner["centroid_dist"], 1e-9)

    #         if abs_gap_amb <= SECONDARY_AMBIGUITY_ABS_MAX and rel_gap_amb <= SECONDARY_AMBIGUITY_REL_MAX:
    #             preferred = PAIR_PREFERENCES.get(winner["topic"], set())
    #             preferred_candidates = [s for s in candidates if s["topic"] in preferred]
    #             other_candidates = [s for s in candidates if s["topic"] not in preferred]
    #             ordered = preferred_candidates + other_candidates

    #             for s in ordered:
    #                 abs_gap = s["centroid_dist"] - winner["centroid_dist"]
    #                 rel_gap = s["centroid_dist"] / max(winner["centroid_dist"], 1e-9)
    #                 if abs_gap <= ROUTER_MAX_ABS_GAP and rel_gap <= ROUTER_MAX_REL_GAP:
    #                     allowed_topics.append(s["topic"])
    #                     break
    
    # Secondary selection with ambiguity gate (NO pair preference)
    if winner["topic"] not in STOP_EARLY_TOPICS and MAX_ALLOWED_TOPICS > 1:
        candidates = [s for s in scored[1:] if s["topic"] not in STOP_EARLY_TOPICS]
        if candidates:
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


    allowed_topics = [t for t in allowed_topics if t and t not in DISALLOWED_OUTPUT_TOPICS]
    allowed_topics = allowed_topics[:MAX_ALLOWED_TOPICS]
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
