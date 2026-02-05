# Intelligent Assistant Platform

Production-grade RAG platform with retrieval, embeddings, and tool integration.

## Dev Quickstart

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Run tests
pytest -q

# Run specific tests
pytest -q tests/test_chunking.py
```

## Architecture Rules

| Layer | Purpose | Constraints |
|-------|---------|-------------|
| `core/` | Pure logic | No DB, no network, no filesystem writes, no timestamps |
| `ingestion/` | File I/O | Reads files, produces Chunks |
| `db/` | Persistence | SQLAlchemy + pgvector |
| `api/` | HTTP boundary | FastAPI |

**Key principle**: `core/` must stay pure and deterministic. All side effects belong in other layers.

## Core Modules

- `core/chunking.py` — Token-based text splitting with tiktoken
- `core/text.py` — Text normalization and markdown extraction
- `core/config.py` — `ChunkingConfig` and presets
- `core/types.py` — Protocols for layer bridging

## Documentation

- [CLAUDE.md](CLAUDE.md) — AI assistant context and rules
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design
- [docs/DECISIONS.md](docs/DECISIONS.md) — Architecture decision records

## Current Status

**Week 1**: Chunking, text extraction, ingestion pipeline.

Next: embeddings, pgvector integration, /search endpoint.
