# Architecture Decision Records (ADR-lite)

Lightweight decision log for significant architectural choices.

---

## ADR-001: Token-based chunking over character-based

**Status**: Accepted
**Date**: 2024-02

**Context**: RAG systems need to split documents into chunks for embedding.

**Decision**: Use token-based chunking with tiktoken.

**Rationale**:
- LLMs process tokens, not characters. 512 tokens = predictable context usage.
- Character chunks vary wildly in token count (100-500 tokens for 512 chars).
- Overlap of N tokens guarantees N tokens of shared context.

---

## ADR-002: Pure core/ layer with no side effects

**Status**: Accepted
**Date**: 2024-02

**Context**: Need clear boundaries between pure logic and I/O.

**Decision**: `core/` contains only pure functions. No DB, no network, no filesystem writes, no timestamps.

**Rationale**:
- Pure functions are trivially testable without mocking.
- Deterministic behavior enables parallel execution.
- Clear boundary makes implementations swappable.

---

## ADR-003: Frozen dataclasses for domain objects

**Status**: Accepted
**Date**: 2024-02

**Context**: Need to represent chunks, configs, and domain objects.

**Decision**: Use `@dataclass(frozen=True)` for all core domain objects.

**Rationale**:
- Immutability prevents accidental mutation bugs.
- Frozen dataclasses are hashable (usable in sets, as dict keys).
- Lighter than Pydantic for internal data structures.

---

## ADR-004: Optional doc_id with content-based default

**Status**: Accepted
**Date**: 2024-02

**Context**: Chunks need a document identifier.

**Decision**: `doc_id` is optional. If not provided, derive from `sha256(source_path + text)[:16]`.

**Rationale**:
- Callers often don't have a pre-existing document ID.
- Content-based ID is deterministic and stable.
- Enables idempotent re-chunking.

---

## ADR-005: ChunkingConfig for parameter bundling

**Status**: Accepted
**Date**: 2024-02

**Context**: `chunk_text()` has multiple optional parameters.

**Decision**: Add `ChunkingConfig` dataclass. Accept either config object or individual params.

**Rationale**:
- Configs can be defined once and reused across pipelines.
- Validation happens at config construction.
- Backwards compatible with individual params.

---

## ADR-006: Protocol-based type bridging between layers

**Status**: Accepted
**Date**: 2024-02

**Context**: `core/chunking.Chunk` and `db/models.Chunk` have different fields.

**Decision**: Define `ChunkProtocol` in `core/types.py` with minimal shared interface.

**Rationale**:
- Protocols enable structural typing without inheritance.
- Explicit conversion makes mapping visible and testable.
- Avoids tight coupling between layers.
