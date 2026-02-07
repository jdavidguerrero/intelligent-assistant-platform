# Architecture Rules

These constraints apply to ALL agents and ALL code changes in this repository.

## Layer Boundaries

```
core/       Pure functions. No DB, no network, no filesystem, no timestamps.
ingestion/  Side effects: file I/O, network calls, orchestration.
db/         SQLAlchemy models, pgvector, persistence layer.
api/        FastAPI HTTP boundary. Thin controllers only.
tests/      Deterministic. No flaky tests. No time-dependent assertions.
```

## Non-Negotiable Constraints

1. **`core/` must stay pure** — No imports from `db/`, `api/`, or `ingestion/`. No `os`, `pathlib`, `requests`, `datetime.now()`, or any I/O.
2. **Type hints everywhere** — All functions must be fully typed.
3. **Frozen dataclasses for data** — Prefer `@dataclass(frozen=True)` for immutable value objects.
4. **Raise on invalid input** — Use `ValueError` for bad input. Never silently return `None`.
5. **Tests validate behavior** — Test invariants and contracts, not implementation details.

## Naming Conventions

- `core/` types: `Chunk`, `ChunkingConfig`, `LoadedDocument` (pure data)
- `db/` models: `ChunkRecord`, `Document` (ORM models, different names from core types)
- No naming collisions across layers — if `core/` has `Chunk`, `db/` must NOT also have `Chunk`

## Dependency Direction

```
api/ → ingestion/ → core/
api/ → db/
ingestion/ → db/
ingestion/ → core/

NEVER: core/ → db/
NEVER: core/ → api/
NEVER: core/ → ingestion/
```

## Integration Path

All agents should evaluate changes against the pipeline:

```
load documents → chunk text → embed chunks → persist to pgvector → search → respond
```

Every recommendation must map to a concrete step in this pipeline.
