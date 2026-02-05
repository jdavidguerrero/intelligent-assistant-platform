# Architecture

## Vision

A production-grade AI assistant platform optimized for:
- **Retrieval quality** over model cleverness
- **Deterministic tools** over LLM reasoning
- **Observability** as a first-class concern
- **Low latency** for real-time interactions

## Layer Boundaries

```
┌─────────────────────────────────────────────────────┐
│                      api/                           │
│         HTTP boundary (FastAPI)                     │
│         Handles auth, validation, routing           │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                   ingestion/                        │
│         File I/O, document parsing                  │
│         Converts files → Chunks                     │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                     core/                           │
│         PURE FUNCTIONS ONLY                         │
│         No DB, no network, no filesystem writes     │
│         Deterministic, testable, swappable          │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│                      db/                            │
│         Persistence layer (PostgreSQL + pgvector)   │
│         SQLAlchemy models, migrations               │
└─────────────────────────────────────────────────────┘
```

## Core Module Design

`core/` contains pure, side-effect-free modules:

| Module | Responsibility |
|--------|----------------|
| `chunking.py` | Token-based text splitting with tiktoken |
| `text.py` | Text normalization and markdown extraction |
| `config.py` | Immutable configuration dataclasses |
| `types.py` | Protocols and type definitions for layer bridging |

**Why pure?** Pure functions are:
- Trivially testable (no mocking)
- Deterministic (same input → same output)
- Parallelizable (no shared state)
- Swappable (easy to replace implementations)

## Data Flow

```
Document (file)
    → ingestion/ reads file, extracts text
    → core/text.py normalizes content
    → core/chunking.py splits into Chunks
    → db/ persists with embeddings
    → api/ serves search results
```

## Key Invariants

1. **Token-based chunking**: `encode(chunk.text) == doc_tokens[token_start:token_end]`
2. **Chunk immutability**: All `Chunk` objects are frozen dataclasses
3. **Config validation**: `ChunkingConfig` validates on construction, not on use
4. **No timestamps in core/**: Timestamps belong in db/ or ingestion/

## Future Additions

- `embeddings/`: Embedding model abstraction (OpenAI, local models)
- `retrieval/`: Vector search, reranking, hybrid search
- `tools/`: MCP tool definitions and handlers
- `agents/`: Orchestration layer for multi-step reasoning
