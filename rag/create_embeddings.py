# rag/create_embeddings.py
import os
from typing import List, Dict

import chromadb
from chromadb.config import Settings
from openai import OpenAI

from rag.registry import ALL_CHUNKS
from rag.validator import validate_chunks
from dotenv import load_dotenv
load_dotenv()


# ---- Config ----
CHROMA_DIR = os.getenv("CHROMA_DIR", ".chroma")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "rag_chunks_v1")

EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")  # good default
BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "64"))


def _batched(xs: List, n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def embed_texts(client: OpenAI, texts: List[str]) -> List[List[float]]:
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [item.embedding for item in resp.data]


def main():
    validate_chunks(ALL_CHUNKS)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    oai = OpenAI(api_key=api_key)

    # Persistent Chroma
    chroma = chromadb.PersistentClient(
        path=CHROMA_DIR,
        settings=Settings(anonymized_telemetry=False),
    )

    # Wipe and recreate collection (no mixed embeddings)
    try:
        chroma.delete_collection(COLLECTION_NAME)
        print(f"🧹 Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    col = chroma.create_collection(
        name=COLLECTION_NAME,
        metadata={"purpose": "router+prompt_rag", "embed_model": EMBED_MODEL},
    )

    # Prepare inputs
    ids = []
    embed_inputs = []
    metadatas: List[Dict] = []
    documents: List[str] = []  # store chunk["text"] here for easy retrieval

    for i, ch in enumerate(ALL_CHUNKS):
        ids.append(f"chunk-{i}")
        embed_inputs.append(ch["data"])      # ✅ embed ONLY data
        documents.append(ch["text"])         # ✅ store text (not embedded)
        metadatas.append(
            {
                "doc_type": ch["doc_type"],
                "topic": ch["topic"],
                "priority": int(ch["priority"]),
                "role": ch["role"],
                "data": ch["data"],          # keep for debugging/preview
                "source": ch.get("source", "clean"),
            }
        )

    # Embed + upsert in batches
    total = len(embed_inputs)
    added = 0

    for batch_ids, batch_inputs, batch_docs, batch_meta in zip(
        _batched(ids, BATCH_SIZE),
        _batched(embed_inputs, BATCH_SIZE),
        _batched(documents, BATCH_SIZE),
        _batched(metadatas, BATCH_SIZE),
    ):
        vectors = embed_texts(oai, batch_inputs)
        col.add(
            ids=batch_ids,
            embeddings=vectors,
            documents=batch_docs,
            metadatas=batch_meta,
        )
        added += len(batch_ids)
        print(f"✅ Embedded {added}/{total}")

    print(f"\n🎉 Done. Collection='{COLLECTION_NAME}', dir='{CHROMA_DIR}', total={total}")


if __name__ == "__main__":
    main()
