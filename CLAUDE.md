# CLAUDE.md — Intelligent Assistant Platform

Constitution for AI assistants working on this codebase. Non-negotiable.

## Identity

**Product**: Intelligent Assistant Platform — production-grade RAG system with retrieval, embeddings, and tool integration.
**Architecture**: Core engine + domain packs. Core is pure logic; domain packs add integrations.
**Current phase**: Week 1 — chunking, text extraction, ingestion pipeline.

## Architectural Spine

```
core/       Pure functions. No side effects. Fully deterministic.
ingestion/  File I/O, network calls, orchestration. Side effects live here.
db/         SQLAlchemy models, pgvector, persistence layer.
api/        FastAPI HTTP boundary. Thin controllers only.
tests/      Pytest suite. Deterministic. No flaky tests.
```

### Dependency Rules

| Layer | Allowed imports | Forbidden imports |
|-------|----------------|-------------------|
| `core/` | stdlib, `tiktoken`, `dataclasses`, `typing` | `db/`, `api/`, `ingestion/`, `sqlalchemy`, `fastapi`, `os.path`, `pathlib`, `requests`, `datetime.now()` |
| `ingestion/` | `core/`, `db/`, stdlib, `openai`, `pathlib` | `api/` |
| `db/` | stdlib, `sqlalchemy`, `pgvector` | `core/`, `api/`, `ingestion/` |
| `api/` | `core/`, `ingestion/`, `db/`, `fastapi` | — |
| `tests/` | everything (test boundary) | — |

### Dependency Direction

```
api/ → ingestion/ → core/
api/ → db/
ingestion/ → db/
ingestion/ → core/

NEVER: core/ → db/
NEVER: core/ → api/
NEVER: core/ → ingestion/
```

## Non-Negotiable Rules

1. **`core/` must stay pure** — No DB, no network, no filesystem writes, no timestamps, no env vars.
2. **Type hints everywhere** — All functions must be fully typed (args + return).
3. **Frozen dataclasses for data** — Prefer `@dataclass(frozen=True)` for immutable value objects.
4. **Tests must be deterministic** — No flaky tests, no time-dependent assertions, no network in tests.
5. **Raise ValueError for invalid input** — Don't silently fail or return `None`.
6. **Docstrings on public functions** — Every exported function must have a docstring.

## Engineering Standards

- Keep modules small and focused (one responsibility per file).
- Avoid global state and singletons.
- Prefer explicit over clever.
- No premature abstractions — wait for the third use case.
- Naming: `core/` types are `Chunk`, `ChunkingConfig`; `db/` models are `ChunkRecord`, `Document`. No collisions.

## Commands

```bash
# Tests
pytest -q                           # all tests
pytest -q tests/test_chunking.py    # specific file

# Lint
ruff check . && ruff format --check .

# Format
ruff format .
```

## PR Discipline

```
branch → implement → lint + test → PR → status checks → review → merge to main
```

- Every change goes through a PR. No direct commits to `main`.
- PRs must pass lint (`ruff`) and tests (`pytest`) before review.
- Reviews use the PR Reviewer agent (`.claude/agents/pr-reviewer.md`).

## When Proposing Changes

1. Explain **what** and **why** briefly.
2. Show the diff or list files changed.
3. Include or update tests.
4. Provide verification command.

## Key Files

| File | Purpose |
|------|---------|
| `core/chunking.py` | Token-based text chunking |
| `core/text.py` | Pure text extraction / normalization |
| `core/config.py` | ChunkingConfig and presets |
| `core/types.py` | Protocols and type definitions |
| `core/embeddings/base.py` | EmbeddingProvider protocol |
| `ingestion/embeddings.py` | OpenAI embedding provider |
| `ingestion/loaders.py` | Document loaders (md, txt) |
| `ingestion/ingest.py` | CLI ingestion pipeline |
| `db/models.py` | SQLAlchemy ORM models |
| `db/session.py` | Session factory + `get_session()` |
| `api/main.py` | FastAPI application |

## AI Collaboration Layer

The `.claude/` directory defines the AI agent system for this repo. See `.claude/README.md` for navigation.
