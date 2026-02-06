# PLAYBOOK — Senior Implementer (Roadmap Execution)

## Scope
Implement roadmap tasks with production boundaries:
- `core/` = pure + deterministic (no DB, no network, no filesystem)
- `ingestion/` = filesystem + orchestration (side effects allowed)
- `db/` = SQLAlchemy models + migrations (if used)
- `api/` = FastAPI endpoints (later)

## Rules
- Prefer typed code (Python 3.12).
- Small commits, PR-ready.
- Add/adjust tests for any `core/` logic.
- For side effects, focus on correctness and clear error messages.
- No premature frameworks: keep it minimal.

## Day 3 Deliverables
1) Embedding service abstraction:
   - Provider interface + OpenAI implementation
   - Sync method ok for now (async later)
   - Config via env vars

2) Ingestion pipeline for md/txt:
   - Load file content
   - (Optional) light normalization
   - Chunk with `core.chunking.chunk_text`
   - Embed each chunk text
   - Persist to Postgres (pgvector)

3) CLI entry point:
   - `python -m ingestion.ingest --data-dir data --limit 10`
   - Prints counts + sample row

## Output format from agent
- Summary
- Files changed
- Commands executed + results
- Next steps
- Minimal patch snippets if needed