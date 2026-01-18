try-rag
=======

Overview
--------
This project builds a retrieval-augmented prompt assembler for a workflow-planning LLM.
It embeds short routing summaries ("data") into a Chroma vector store, uses those
embeddings to route a user query to the most relevant rule topics, expands related
support rules, and assembles a final prompt that drives a planner model to output a
structured workflow plan in Markdown.

The core flow is:
- Curate chunk rules in `data/rag_chunks_data_clean.py`
- Validate and embed chunk data into Chroma
- Route a query to relevant topics via embeddings
- Assemble a prompt (core + router + support + user query)
- Send the prompt to an LLM to produce the workflow plan

Project layout
--------------
- `rag/`
  - `router.py`: Embedding-based topic routing with priority and guardrails.
  - `assembler.py`: Builds the final prompt from core, router, and support chunks.
  - `support_expander.py`: Expands selected topics into related support chunks.
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
- `tests/`
  - Router and prompt assembly tests.
- `planner.py`: Full agent/backstory prompt source used by chunk data (long text).
- `main.py`: Minimal entry point stub.

Key concepts
------------
- Chunk format:
  - `doc_type`: CORE / RULE / CATALOG
  - `topic`: Routing topic (e.g., `data_extraction`, `conditions`)
  - `priority`: Higher wins on near-ties
  - `role`: `router`, `support`, or `static`
  - `data`: Short summary that gets embedded
  - `text`: Full content inserted into prompts
- Embeddings:
  - Only `data` is embedded for retrieval.
  - `text` is stored in Chroma documents for prompt assembly and debugging.
- Routing:
  - `rag/router.py` embeds the query, retrieves candidate chunks, groups by topic,
    and applies thresholds to select one or more topics.
  - Stop-early topics (e.g., `user_mgmt`, `static_vs_dynamic`) short-circuit routing.
- Prompt assembly:
  - `rag/assembler.py` always injects core/static content.
  - It then inserts router topics and related support chunks.
  - The user query is appended at the end as `USER.QUERY`.

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
This creates a fresh Chroma collection from `data/rag_chunks_data_clean.py`.
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
- Retrieval queries are prevented from being routed to action-CRUD topics.
- Prompt assembly deduplicates blocks by text hash and prevents router/support
  duplication.

How chunking works
------------------
Chunks are not produced by an automated splitter; they are authored and curated
manually in `data/rag_chunks_data_clean.py`. Each chunk is a dict with a fixed
schema:
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

How retrieval builds the final prompt
-------------------------------------
1) **Embeddings index**
   - `rag/create_embeddings.py` validates chunks and embeds only `chunk["data"]`.
   - Embeddings are stored in Chroma; `chunk["text"]` is stored as the document
     payload for later inclusion in prompts.

2) **Query routing**
   - `rag/router.py` embeds the user query and performs a vector search in the
     Chroma collection (`TOP_K` results).
   - It filters to `role == "router"` chunks, keeps the top `TOP_ROUTER`, then
     groups by `(doc_type, topic, role)` and keeps the best distance per group.
   - Priority is used as a tie-breaker when distances are within
     `PRIORITY_EPSILON`.
   - It applies distance-gap thresholds (`ROUTER_MAX_ABS_GAP`,
     `ROUTER_MAX_REL_GAP`, `ROUTER_MIN_GAP_TO_ALLOW_MULTI`) to allow one or more
     topics, capped by `MAX_ALLOWED_TOPICS`.
   - Stop-early topics (`user_mgmt`, `static_vs_dynamic`) short-circuit routing.
   - Retrieval-style queries are prevented from routing to CRUD action topics,
     and fall back to retrieval topics when needed.

3) **Support expansion**
   - `rag/support_expander.py` expands the selected router topics into related
     support topics (e.g., conditions/loops or planner policy), but only for
     allowed topics and with rules to avoid over-including catalogs.

4) **Prompt assembly**
   - `rag/assembler.py` always injects static CORE chunks first.
   - It then inserts router chunks for the allowed topics, followed by support
     chunks.
   - Router and support blocks are deduplicated by text hash to avoid repeats.
   - The user query is appended at the end under a `USER.QUERY` header.
