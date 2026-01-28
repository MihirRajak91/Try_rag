import argparse
import os
from typing import Any, Dict, List

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


def _get_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )


def _embed_texts(oai: OpenAI, texts: List[str]) -> List[List[float]]:
    resp = oai.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def build_index(recreate: bool = False) -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)
    client = _get_client()

    if recreate:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    col = client.get_or_create_collection(name=COLLECTION_NAME)

    texts: List[str] = []
    metadatas: List[Dict[str, Any]] = []
    ids: List[str] = []

    for i, ch in enumerate(chunk_data):
        data = (ch.get("data") or "").strip()
        if not data:
            continue

        cid = f"chunk-{i+1}"
        ids.append(cid)
        texts.append(data)
        metadatas.append(
            {
                "doc_type": ch.get("doc_type"),
                "topic": ch.get("topic"),
                "priority": int(ch.get("priority", 0)),
                "role": ch.get("role"),
            }
        )

    embeddings = _embed_texts(oai, texts)

    # Upsert to avoid duplicate IDs if collection already exists
    col.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,  # only `data` is embedded and stored
        metadatas=metadatas,
    )

    print(f"✅ Indexed {len(ids)} chunks into '{COLLECTION_NAME}' at '{CHROMA_DIR}'.")


def query_top_k(query: str, top_k: int = TOP_K) -> List[Dict[str, Any]]:
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
        include=["distances", "metadatas", "documents"],
    )

    ids = (res.get("ids") or [[]])[0] or []
    dists = (res.get("distances") or [[]])[0] or []
    metas = (res.get("metadatas") or [[]])[0] or []
    docs = (res.get("documents") or [[]])[0] or []

    out: List[Dict[str, Any]] = []
    for cid, dist, meta, doc in zip(ids, dists, metas, docs):
        out.append(
            {
                "id": cid,
                "distance": float(dist),
                "doc_type": (meta or {}).get("doc_type"),
                "topic": (meta or {}).get("topic"),
                "role": (meta or {}).get("role"),
                "priority": (meta or {}).get("priority"),
                "data": doc,
            }
        )

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple RAG (data-only embedding) query tool")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the Chroma collection from data")
    parser.add_argument("--query", type=str, help="User query to retrieve top-k chunks")
    parser.add_argument("--top-k", type=int, default=TOP_K, help="Number of chunks to retrieve")

    args = parser.parse_args()

    if args.rebuild:
        build_index(recreate=True)

    if args.query:
        results = query_top_k(args.query, top_k=args.top_k)
        print("\n=== TOP MATCHES ===")
        for i, r in enumerate(results, start=1):
            print(f"{i:>2}. id={r['id']}  dist={r['distance']:.4f}")
            print(
                f"    doc_type={r['doc_type']}  topic={r['topic']}  role={r['role']}  priority={r['priority']}"
            )
            if r.get("data"):
                data_line = (r["data"] or "").splitlines()[0][:120]
                print(f"    data='{data_line}'")
            print()

    if not args.rebuild and not args.query:
        parser.print_help()


if __name__ == "__main__":
    main()
