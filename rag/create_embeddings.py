import os
import json
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
from openai import OpenAI

load_dotenv()

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_PERSIST_DIR", os.getenv("CHROMA_DIR", ".chroma"))
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_chunks_v1")
EMBED_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", os.getenv("EMBED_MODEL", "text-embedding-3-small"))

# Where to write centroids (requested)
CENTROIDS_PATH = os.path.join(CHROMA_DIR, "topic_centroids.json")

# Import your chunk registry (adjust import if your file name differs)
# Expected: chunk_data = [ {doc_type, topic, priority, role, data, text}, ... ]
from data.rag_chunks_data_clean import chunk_data


def _embed_texts(oai: OpenAI, texts: List[str]) -> List[List[float]]:
    # Batched embedding for speed + stability
    resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _avg_vectors(vectors: List[List[float]]) -> List[float]:
    if not vectors:
        return []
    dim = len(vectors[0])
    out = [0.0] * dim
    for v in vectors:
        for i, x in enumerate(v):
            out[i] += float(x)
    n = float(len(vectors))
    return [x / n for x in out]


def build_centroids(router_items: List[Tuple[str, Dict[str, Any], List[float]]]) -> Dict[str, List[float]]:
    """
    router_items: list of (chunk_id, meta, embedding)
    Returns: { topic: centroid_embedding }
    """
    by_topic: Dict[str, List[List[float]]] = {}
    for _cid, meta, emb in router_items:
        topic = (meta or {}).get("topic")
        if not topic:
            continue
        by_topic.setdefault(topic, []).append(emb)

    centroids: Dict[str, List[float]] = {}
    for topic, vecs in by_topic.items():
        centroids[topic] = _avg_vectors(vecs)

    return centroids


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)

    chroma = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )

    # Recreate collection cleanly
    try:
        chroma.delete_collection(COLLECTION_NAME)
        print(f"🧹 Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    col = chroma.get_or_create_collection(name=COLLECTION_NAME)

    # Prepare docs to embed: ONLY `data` is embedded
    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    for i, ch in enumerate(chunk_data):
        data = (ch.get("data") or "").strip()
        if not data:
            continue

        # stable chunk id
        cid = f"chunk-{i+1}"

        meta = {
            "doc_type": ch.get("doc_type"),
            "topic": ch.get("topic"),
            "priority": int(ch.get("priority", 0)),
            "role": ch.get("role"),
        }

        texts.append(data)
        metadatas.append(meta)
        ids.append(cid)

    # Embed and add to Chroma
    embeddings = _embed_texts(oai, texts)

    col.add(
        ids=ids,
        embeddings=embeddings,
        documents=texts,      # keep embedded text for inspect/debug
        metadatas=metadatas,
    )

    # Build centroids from router chunks only
    router_items: List[Tuple[str, Dict[str, Any], List[float]]] = []
    for cid, meta, emb in zip(ids, metadatas, embeddings):
        if (meta or {}).get("role") == "router":
            router_items.append((cid, meta, emb))

    centroids = build_centroids(router_items)

    os.makedirs(CHROMA_DIR, exist_ok=True)
    with open(CENTROIDS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "collection": COLLECTION_NAME,
                "embed_model": EMBED_MODEL,
                "centroids": centroids,
            },
            f,
            ensure_ascii=False,
        )

    print(f"✅ Embedded {len(ids)}/{len(ids)}")
    print(f"\n🎉 Done. Collection='{COLLECTION_NAME}', dir='{CHROMA_DIR}', total={len(ids)}")
    print(f"🧠 Wrote centroids: {CENTROIDS_PATH} (topics={len(centroids)})")


if __name__ == "__main__":
    main()
