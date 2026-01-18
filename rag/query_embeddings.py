# rag/query_embeddings.py
import os
from dotenv import load_dotenv

import chromadb
from chromadb.config import Settings
from openai import OpenAI

load_dotenv()

# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_DIR", ".chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION")

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
TOP_K = int(os.getenv("QUERY_TOP_K", "8"))


def embed_query(oai: OpenAI, text: str):
    resp = oai.embeddings.create(model=EMBED_MODEL, input=[text])
    return resp.data[0].embedding


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found (check .env)")

    oai = OpenAI(api_key=api_key)

    chroma = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )
    col = chroma.get_collection(name=COLLECTION_NAME)

    query = input("Enter query: ").strip()
    if not query:
        print("Empty query. Exiting.")
        return

    qvec = embed_query(oai, query)

    res = col.query(
        query_embeddings=[qvec],
        n_results=TOP_K,
        include=["distances", "metadatas", "documents"],
    )

    ids = res.get("ids", [[]])[0]
    dists = res.get("distances", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    print("\n=== TOP MATCHES ===")
    for i, (cid, dist, meta) in enumerate(zip(ids, dists, metas), start=1):
        doc_type = meta.get("doc_type")
        topic = meta.get("topic")
        role = meta.get("role")
        priority = meta.get("priority")
        data_label = (meta.get("data") or "").splitlines()[0][:90]

        print(f"{i:>2}. id={cid}  dist={dist:.4f}")
        print(f"    doc_type={doc_type}  topic={topic}  role={role}  priority={priority}")
        if data_label:
            print(f"    data='{data_label}'")
        print()

if __name__ == "__main__":
    main()
