# Implementer Agent Memory

## Project Quick Ref

- Python 3.12.2 — use `datetime.UTC` (UP017), `zip(..., strict=False)` (B905)
- All ruff auto-fixes: run `ruff check --fix` then `ruff check` to confirm zero errors
- Pre-existing test failures (do NOT investigate): `test_mcp_server.py`, `test_mcp_search_handler.py`, `test_golden_set.py` (need network/DB)

## Layer Boundaries (enforced by ruff)

- `core/` — stdlib only. No `os`, `pathlib`, `datetime.now()`, no imports from db/ingestion/api
- `ingestion/` — can import `core/`, `db/`, stdlib, `openai`, `pathlib`
- `db/` — stdlib + sqlalchemy + pgvector. NO core/ imports
- New `core/memory/` package: pure value objects + deterministic functions only

## Memory System (Days 1-2 — shipped)

Day 1 files:
- `core/memory/__init__.py` — empty package marker
- `core/memory/types.py` — MemoryEntry frozen dataclass, MemoryType Literal, DECAY_DAYS dict
- `core/memory/decay.py` — compute_decay_weight(), filter_active_memories() — all take `now` as param
- `core/memory/format.py` — format_memory_block() — bullet format, no citation numbers
- `ingestion/memory_store.py` — SQLite CRUD + cosine search + decay weighting
- Day 1 tests: 56 tests, all green

Day 2 files:
- `ingestion/memory_extractor.py` — rule-based + LLM extraction. extract_memories() NEVER raises.
- Day 2 tests: 27 tests, all green

## GenerationResponse Fields (CRITICAL)
`core/generation/base.GenerationResponse` uses:
- `usage_input_tokens: int` and `usage_output_tokens: int` (NOT `usage: dict`)
- Task specs/examples may show `usage={"prompt_tokens": ...}` — that is WRONG, use the int fields

## Common Lint Issues to Pre-empt

- `datetime.timezone.utc` → use `datetime.UTC` (UP017)
- `zip(a, b)` → `zip(a, b, strict=False)` (B905)
- Import sorting: stdlib first, then third-party, then local (I001)
- Remove unused imports before submitting (F401)
