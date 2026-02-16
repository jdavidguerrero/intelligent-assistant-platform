# Refactorer Agent Memory

## Safety Protocol

- Always run `pytest -q` BEFORE any change (green baseline required)
- Always run `pytest -q` AFTER every change (green-to-green)
- One concern per refactor — never bundle unrelated changes
- If more than 5 files change, break into phases

## Naming Conventions

### Cross-Layer Naming (No Collisions)
- `core/` types: `Chunk`, `ChunkingConfig`, `LoadedDocument`
- `db/` models: `ChunkRecord`, `Document`
- Rule: If core/ has `Chunk`, db/ must NOT also have `Chunk`

## Common Refactor Patterns

### Pure String Replacement for os.path
- `os.path.basename(path)` → `path.rstrip("/").split("/")[-1]`
- Edge cases: empty string, root path "/", trailing slashes
- Must add tests for all edge cases

### Session Consolidation
- Single source: `db/session.py` exports `SessionLocal`
- Other modules import, never recreate `create_engine()`
- Anti-pattern: duplicate `sessionmaker()` across modules

### Import Direction Fixes
- Check: `core/` must never import from `db/`, `api/`, `ingestion/`
- Check: `db/` must never import from `core/`, `api/`, `ingestion/`
- Allowed: `ingestion/` → `core/`, `ingestion/` → `db/`, `api/` → everything

## What NOT to Refactor

- Database schema metadata (`__table_args__`, indexes) — no runtime behavior
- Trivial import reordering with identical behavior
- Working code that doesn't violate boundaries
