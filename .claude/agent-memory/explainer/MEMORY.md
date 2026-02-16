# Explainer Agent Memory

## Pipeline Context

Full pipeline: load → chunk → embed → persist → search → respond

Every explanation must map code to its position in this pipeline.

## Key Invariants (Reference)

### Chunking
- Token-based via tiktoken `cl100k_base` encoding
- `encode(chunk.text) == doc_tokens[token_start:token_end]`
- Overlap: `next.token_start == current.token_end - overlap`
- Coverage: first chunk starts at 0, last ends at total_tokens

### Embeddings
- Provider: OpenAI `text-embedding-3-small` (1536 dimensions)
- Deterministic provider protocol in `core/embeddings/base.py`
- Fake provider pattern for testing: `_FakeEmbeddingProvider`

### Storage
- pgvector with HNSW index (`m=16`, `ef_construction=64`, `vector_cosine_ops`)
- Cosine similarity via `<=>` operator
- Score filtering is API-layer concern, not DB-layer

## Explanation Patterns

### When Explaining core/ Code
- Emphasize purity: no side effects, fully deterministic
- Show input → output mapping
- List invariants that must hold
- Mention what tests validate

### When Explaining API Endpoints
- Trace from HTTP request to DB query and back
- Show dependency injection chain
- Note thin controller pattern (no business logic in route)

### When Explaining Diffs
- Focus on WHY, not just WHAT changed
- Map changes to pipeline steps
- Flag any boundary violations introduced
