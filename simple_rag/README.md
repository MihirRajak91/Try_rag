Simple RAG
==========

Overview
--------
This folder contains a standalone, data-only RAG pipeline:

- Embeds ONLY the `data` field from `data/rag_chunks_data_clean.py` into Chroma.
- Retrieves top-K chunks by vector similarity.
- Assembles a simple prompt (core + always blocks + retrieved chunks + USER.QUERY).
- Runs a planner model and normalizes the output to enforce formatting rules.

Files
-----
- `simple_rag.py` — build/query the Chroma collection (data-only embedding)
- `simple_assembler.py` — builds the prompt from retrieved chunks
- `run_simple_planner.py` — runs the LLM planner with the assembled prompt
- `plan_normalizer.py` — post-processes planner output to match the contract

Environment Variables
---------------------
Required:
- `OPENAI_API_KEY`
- `CHROMA_PERSIST_DIR` (or `CHROMA_DIR`)
- `CHROMA_COLLECTION`

Planner settings:
- `LLM_MODEL` (default: gpt-4o-mini)
- `LLM_TEMPERATURE` (default: 0.2)

Retrieval settings:
- `QUERY_TOP_K` (default: 8)
- `SIMPLE_RAG_MAX_BLOCKS` (default: 10)

Routing heuristics (simple guardrails):
- `SIMPLE_RAG_LOOPS_MAX_ABS_GAP` (default: 0.20)
- `SIMPLE_RAG_CONDITIONS_MAX_ABS_GAP` (default: 0.12)
- `SIMPLE_RAG_ACTIONS_MAX_ABS_GAP` (default: 0.05)
- `SIMPLE_RAG_STATIC_MAX_ABS_GAP` (default: 0.05)
- `SIMPLE_RAG_STATIC_MIN_GAP_OVER_ACTIONS` (default: 0.05)

How it Works
------------
1) Index data-only summaries
   - `simple_rag.py --rebuild` embeds only the `data` field of each chunk.

2) Retrieve top-K
   - Query embedding is compared to chunk summaries in Chroma.

3) Assemble prompt
   - Core/static blocks
   - Always blocks (planner_policy, output_contract, triggers, etc.)
   - Retrieved chunks
   - USER.QUERY
   - Conditions/loops enforcement blocks when required

4) Plan + normalize
   - `run_simple_planner.py` sends the prompt to the planner model.
   - `plan_normalizer.py` enforces strict output structure (steps/conditions/loops).

Commands
--------
Rebuild embeddings:
```
uv run python simple_rag/simple_rag.py --rebuild
```

Query top-K matches:
```
uv run python simple_rag/simple_rag.py --query "your query" --top-k 8
```

Run planner (assembled prompt → workflow plan):
```
uv run python simple_rag/run_simple_planner.py
```

Notes
-----
- The system is intentionally simple: no centroids, no router model, no keyword rules.
- Output normalization is used to enforce strict formatting and edge-case cleanup.
- If you change `data/rag_chunks_data_clean.py`, rebuild embeddings.
