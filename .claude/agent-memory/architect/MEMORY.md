# Architect Agent Memory

## Layer Boundaries

### Core Purity Rules
- `core/` must NEVER import from `db/`, `api/`, or `ingestion/`
- No I/O operations: no `os`, `pathlib`, `requests`, `datetime.now()`
- Only pure functions with deterministic outputs

### Dependency Flow
```
api/ → ingestion/ → core/
api/ → db/
ingestion/ → db/
```

### Naming Conventions to Prevent Collisions
- `core/` types: `Chunk`, `ChunkingConfig`, `LoadedDocument` (pure data)
- `db/` models: `ChunkRecord`, `Document` (ORM models)
- Rule: Different names for different layers to avoid confusion

## Common Patterns

### When Filtering Should Live in API vs DB Layer
- **API layer filtering (post-retrieval)**: When filter logic is presentation/business logic that might change independently of the query
- **DB layer filtering (SQL WHERE clause)**: When filter is stable, performance-critical, and reduces network transfer

### Score-Based Filtering Pattern
- Similarity scores are domain logic that belong at the API boundary
- DB returns raw results with scores
- API applies thresholds and presentation logic
- Example: min_score filtering should be API-layer, not DB-layer

## Review Checklist

1. Check import directions (never core → impure layers)
2. Verify naming consistency across layers
3. Confirm side effects live outside core/
4. Validate tests are deterministic
5. Ensure changes map to the pipeline: load → chunk → embed → persist → search → respond

## Decision Patterns

### Adding Optional Response Fields
- Use `field: Type | None = None` for optional fields that provide context
- Document when field is populated vs None
- Example: `reason: str | None = None` for explaining empty results

### Parameter Validation
- Use Pydantic Field() with ge/le for numeric ranges
- Use @field_validator for custom logic
- Raise ValueError for invalid inputs (matches core/ convention)
