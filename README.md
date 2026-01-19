try-rag
=======

Overview
--------
This project builds a prompt for a workflow-planning LLM using retrieval-augmented
generation (RAG). It stores short routing summaries in a Chroma vector store, uses
those embeddings to pick the best topics for a user query, expands related support
rules, and assembles a final prompt that the planner model uses to output a
structured workflow plan in Markdown.

In plain terms:
- You write small, curated rule chunks.
- The system embeds the short summaries of those chunks.
- A query is routed to the best-matching topics.
- The full rule text is assembled into one prompt.
- The planner LLM returns a workflow plan.

Project layout
--------------
- `rag/`
  - `router.py`: Embedding-based topic routing with guardrails.
  - `assembler.py`: Builds the final prompt from core, router, and support chunks.
  - `support_expander.py`: Expands router topics into related support chunks.
  - `registry.py`: Merges clean chunk data with any legacy chunk sources.
  - `create_embeddings.py`: Validates and embeds chunk data into Chroma.
  - `query_embeddings.py`: Debug tool to inspect embedding matches.
  - `validator.py`: Schema checks for chunk integrity.
- `data/`
  - `rag_chunks_data_clean.py`: Authoritative chunk registry (router/support/core).
  - `rag_chunks.py`: Legacy chunk source (optional; loaded if present).
- `scripts/`
  - `run_planner.py`: End-to-end prompt assembly + LLM call.
  - `smoke_planner.py`: Quick prompt preview.
- `tests/`: Router and prompt assembly tests.
- `planner.py`: Full agent/backstory prompt source used by chunk data (long text).
- `main.py`: Minimal entry point stub.

Key concepts (simple explanations)
----------------------------------
- Chunk:
  - A small, curated rule unit with a short summary and a full text block.
  - Summary is used for retrieval; full text is inserted into the final prompt.
- Topic routing:
  - The system matches the user query to the most relevant topics using embeddings.
  - It limits how many topics can be selected and blocks unsafe or irrelevant ones.
- Support expansion:
  - After routing, related helper topics are added (e.g., planner policy or loops).
- Prompt assembly:
  - Core/static rules are always included.
  - Router topics and support topics are included next.
  - The user query is appended at the end under `USER.QUERY`.

Setup
-----
Requirements: Python 3.11+

Install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Environment variables (use `.env`):
```text
OPENAI_API_KEY=...
CHROMA_DIR=.chroma
CHROMA_COLLECTION=workflow_rules_v1
EMBED_MODEL=text-embedding-3-small
```

Other optional environment variables:
```text
ROUTER_TOP_K=12
TOP_ROUTER=8
ROUTER_MAX_ABS_GAP=0.28
ROUTER_MAX_REL_GAP=1.35
ROUTER_MIN_GAP_TO_ALLOW_MULTI=0.08
MIN_GROUP_SIZE=1
PRIORITY_EPSILON=0.03
MAX_ALLOWED_TOPICS=2
QUERY_TOP_K=8
EMBED_BATCH_SIZE=64
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.2
```

Build embeddings
----------------
Creates a fresh Chroma collection from `data/rag_chunks_data_clean.py`.
```bash
python rag/create_embeddings.py
```

Inspect embedding matches
-------------------------
```bash
python rag/query_embeddings.py
```

Assemble a prompt
-----------------
```bash
python rag/assembler.py
```

Run the planner end-to-end
--------------------------
```bash
python scripts/run_planner.py
```

Testing
-------
```bash
pytest
```

Notes and conventions
---------------------
- `data/rag_chunks_data_clean.py` is the authoritative source of chunks.
- `data/rag_chunks.py` is optional legacy input; `rag/registry.py` merges it but
  prefers the clean version.
- Routing favors lower embedding distance and higher priority in near ties.
- Retrieval queries are prevented from routing to action-CRUD topics.
- Prompt assembly deduplicates blocks by text hash and prevents router/support
  duplication.

How chunking works (simple view)
--------------------------------
Chunks are authored manually in `data/rag_chunks_data_clean.py`. Each chunk is a
small dict with a fixed schema:
- `doc_type`: logical family (CORE/RULE/CATALOG)
- `topic`: routing topic key (e.g., `data_extraction`, `conditions`)
- `priority`: numeric rank used for tie-breaking
- `role`: `router`, `support`, or `static`
- `data`: short routing summary (this is embedded)
- `text`: full prompt content (this is inserted into the final prompt)

The file groups chunks into layers (core, stop-early gates, data extraction,
CRUD, conditions, notifications, loops, trigger catalog, planner policy) and
then flattens them into the `chunk_data` list. `rag/registry.py` normalizes and
merges this clean list with any legacy chunk list from `data/rag_chunks.py`,
preferring the clean version.

Complete retrieval + assembly flow (plain language)
---------------------------------------------------
1) Chunk registration and validation
   - `data/rag_chunks_data_clean.py` defines the authoritative chunks.
   - `rag/registry.py` merges clean chunks with any legacy ones and normalizes
     them into a single list.
   - `rag/validator.py` enforces the schema so every chunk has the fields needed
     for routing and assembly.

2) Embeddings index
   - `rag/create_embeddings.py` embeds only the short `chunk["data"]` summary.
   - The full `chunk["text"]` is stored as the Chroma document payload so it can
     be inserted into the final prompt later.

3) Query routing (retrieval)
   - `rag/router.py` embeds the user query and searches the Chroma collection.
   - It keeps only `role == "router"` results, then groups by `(doc_type, topic)`.
   - For each group, the best (lowest-distance) result wins; priority breaks
     near-ties using `PRIORITY_EPSILON`.
   - Gap rules (`ROUTER_MAX_ABS_GAP`, `ROUTER_MAX_REL_GAP`,
     `ROUTER_MIN_GAP_TO_ALLOW_MULTI`) decide whether to pick one topic or a few,
     capped by `MAX_ALLOWED_TOPICS`.
   - Stop-early topics (e.g., `user_mgmt`, `static_vs_dynamic`) short-circuit
     routing to avoid over-expanding unrelated rules.
   - Retrieval-style queries are prevented from routing to CRUD action topics
     and are redirected to safer retrieval topics when needed.

4) Support expansion
   - `rag/support_expander.py` takes the chosen router topics and adds related
     support topics (e.g., conditions, loops, planner policy) when allowed.
   - It avoids over-including catalogs or unrelated sections.

5) Prompt assembly
   - `rag/assembler.py` builds the final prompt in a fixed order:
     1) core/static chunks (always included)
     2) selected router chunks
     3) expanded support chunks
     4) the user query appended under `USER.QUERY`
   - Router and support blocks are deduplicated by text hash to avoid repeats.
   - The assembled prompt is ready for the planner LLM to produce a workflow.
