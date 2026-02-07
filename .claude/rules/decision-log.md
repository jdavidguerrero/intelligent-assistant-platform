# Decision Log

Architectural decisions for this repository. Append-only. Format: `DL-###`.

## Template

```
### DL-###: [Title]
**Date**: YYYY-MM-DD
**Status**: Accepted | Superseded | Deprecated
**Context**: What problem or question prompted this decision?
**Decision**: What was decided?
**Rationale**: Why this choice over alternatives?
**Consequences**: What does this enable or constrain?
```

---

## Decisions

### DL-001: core/ Purity Boundary

**Date**: 2025-01-01
**Status**: Accepted
**Context**: The platform needs a kernel of logic (chunking, text processing, config) that is testable, portable, and free of infrastructure coupling.
**Decision**: `core/` must contain only pure, deterministic functions. No DB, no network, no filesystem, no timestamps, no env vars.
**Rationale**: Pure modules are trivially testable, easy to reason about, and can be reused across different deployment targets. Impure dependencies (DB, network) change frequently; core logic should not.
**Consequences**: All side effects must live in `ingestion/`, `db/`, or `api/`. Core types (`Chunk`, `ChunkingConfig`) are frozen dataclasses. Any new `core/` code must pass the purity check: no imports from impure layers.

---

### DL-002: Token-Based Chunking with tiktoken

**Date**: 2025-01-01
**Status**: Accepted
**Context**: Text must be split into chunks for embedding. Character-based splitting is imprecise; sentence splitting is fragile across document types.
**Decision**: Use token-based chunking via `tiktoken` with the `cl100k_base` encoding (GPT-4 / text-embedding-3-small tokenizer).
**Rationale**: Token counts directly map to model context windows and embedding input limits. Using the same tokenizer as the embedding model eliminates mismatch bugs. tiktoken is fast (Rust-backed) and deterministic.
**Consequences**: Chunk sizes are specified in tokens, not characters. Overlap is token-based. Tests must validate token-count invariants (total tokens, overlap correctness, no gaps). Switching embedding models may require re-evaluating the encoding.

---

### DL-003: pgvector + HNSW for Retrieval Storage

**Date**: 2025-01-01
**Status**: Accepted
**Context**: Embedded chunks need to be stored and retrieved by similarity. Options: pgvector (Postgres extension), Pinecone (managed), Qdrant (self-hosted), FAISS (in-memory).
**Decision**: Use pgvector as a Postgres extension with HNSW indexing for approximate nearest neighbor search.
**Rationale**: pgvector keeps vectors alongside relational data in a single database — no sync between two systems. HNSW provides sub-linear query time with tunable recall. Postgres is already in the stack for metadata storage. Managed vector DBs add cost and operational complexity we don't need at this scale.
**Consequences**: `db/models.py` uses `Vector(1536)` column type. Embedding dimension is fixed at 1536 (`text-embedding-3-small`). Index creation uses `HNSW` with `vector_cosine_ops`. Switching to a dedicated vector DB later would require migrating the persistence layer but would not affect `core/` or `ingestion/` logic.
