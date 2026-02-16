# Implementer Agent Memory

## Environment

- Python 3.12.2 via pyenv
- Virtual env: `.venv/`
- Lint: `ruff check . && ruff format --check .`
- Test: `pytest -q`

## Layer Rules (Quick Ref)

- `core/` — Pure only. No os, pathlib, datetime.now, env vars, DB, network.
- `ingestion/` — Side effects allowed. Imports core/ and db/.
- `db/` — SQLAlchemy + pgvector only. No core/ imports.
- `api/` — FastAPI thin controllers. Imports everything.

## Patterns Learned

### FastAPI Dependencies
- Use `Annotated[Type, Depends(fn)]` pattern to avoid ruff B008
- Singleton providers: `global _provider` with lazy init in `api/deps.py`
- Override pattern for tests: `app.dependency_overrides[get_db] = ...`

### Testing Patterns
- SQLite cannot run pgvector operators (`<=>`) — mock `search_chunks` via `patch()`
- Class-based test organization: `class TestFoo:`
- `_FakeEmbeddingProvider` for deterministic embedding tests
- Always run full suite after changes, not just new tests

### Common Lint Issues
- `ingestion/embeddings.py` has pre-existing lint errors (E402, I001) — not our code to fix
- ruff B008: `Depends()` in default args — fix with Annotated pattern

## Ship Checklist

1. Restate task and ship criteria
2. Propose plan (max 6 bullets)
3. Implement with minimal surface area
4. Run `ruff check .` — fix all issues
5. Run `pytest -q` — all green
6. Verify import directions
7. List files changed with brief description
