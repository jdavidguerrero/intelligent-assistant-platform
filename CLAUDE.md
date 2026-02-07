# CLAUDE.md — Intelligent Assistant Platform

This file provides context and rules for AI assistants working on this codebase.

## Project Overview

Production-grade RAG platform with retrieval, embeddings, and tool integration.

**Current phase**: Week 1 — chunking, text extraction, ingestion pipeline.

## Directory Structure

```
core/       Pure functions, no side effects, fully deterministic
ingestion/  File I/O, produces Chunks from documents
db/         SQLAlchemy models, pgvector, persistence
api/        FastAPI HTTP boundary
tests/      Pytest test suite
```

## Non-Negotiable Rules

1. **core/ must stay pure** — No DB, no network, no filesystem writes, no timestamps.
2. **Type hints everywhere** — All functions must be fully typed.
3. **Dataclasses for data** — Prefer `@dataclass(frozen=True)` for immutable data.
4. **Tests must be deterministic** — No flaky tests, no time-dependent assertions.
5. **Raise ValueError for invalid input** — Don't silently fail or return None.

## Commands

```bash
# Run all tests
pytest -q

# Run specific test file
pytest -q tests/test_chunking.py

# Lint (when configured)
ruff check . && ruff format .
```

## Coding Standards

- Keep modules small and focused (one responsibility per file).
- Avoid global state and singletons.
- Docstrings required for all public functions.
- Prefer explicit over clever.
- No premature abstractions — wait for the third use case.

## When Proposing Changes

1. Explain **what** and **why** briefly.
2. Show the diff or list files changed.
3. Include or update tests.
4. Provide verification command.

## Key Files

| File | Purpose |
|------|---------|
| `core/chunking.py` | Token-based text chunking |
| `core/text.py` | Pure text extraction/normalization |
| `core/config.py` | ChunkingConfig and presets |
| `core/types.py` | Protocols and type definitions |
| `db/models.py` | SQLAlchemy ORM models |
| `api/main.py` | FastAPI application |

## Sub-Agents

This repo uses Claude Code sub-agents (`.claude/agents/`). Run `/agents` to see all available agents.

| Agent | Role | Model | Permissions |
|-------|------|-------|-------------|
| `architect` | Architecture review, layer boundaries | sonnet | read-only |
| `pr-reviewer` | PR review, correctness, test quality | sonnet | read-only |
| `explainer` | Code explanation, understanding | sonnet | read-only |
| `implementer` | Build features, ship code | inherit | read-write |
| `test-guardian` | Test coverage, quality enforcement | sonnet | read-write |
| `refactorer` | Safe structural improvements | inherit | read-write |

## Standard Workflows

Reference patterns for multi-agent task sequences.

**Feature Development**: Architect → Implementer → Test Guardian → PR Reviewer

**PR Lifecycle**: Explainer → PR Reviewer → (fix if needed) → re-review

**Architecture Change**: Architect → Refactorer → Test Guardian → Architect → PR Reviewer

**Rules**:
- Max 2 review cycles before human escalation.
- Never skip Test Guardian after implementation.
- If Architect says NEEDS ADJUSTMENT, fix design before writing code.
- Never combine architecture changes with feature work in the same PR.
