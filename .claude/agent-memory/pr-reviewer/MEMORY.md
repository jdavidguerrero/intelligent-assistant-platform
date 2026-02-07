# PR Reviewer Memory

## Common Patterns

### core/ Purity Violations
- `os.path.basename()` is I/O-adjacent and violates purity
- Safe replacement: `path.rstrip("/").split("/")[-1]`
- Always test edge cases: empty string, root path, trailing slashes
- Verify with automated import checker (check for `os`, `pathlib`, `datetime`, etc.)

### Session Management Anti-Pattern
- Duplicate `create_engine()` + `sessionmaker()` across modules creates connection pool fragmentation
- Single source of truth: `db/session.py` exports `SessionLocal`
- Other modules import, never recreate

### HNSW Index Parameters (pgvector)
- Standard config: `m=16, ef_construction=64` for balanced performance
- Always specify `vector_cosine_ops` for cosine similarity
- Index name convention: `idx_{table}_{column}_hnsw`

## Review Workflow

1. `git diff` first to see scope
2. Read modified files in full
3. Run tests to verify correctness
4. Check edge cases with manual testing
5. Verify linting passes
6. Check dependency directions with automated script
7. Evaluate against architecture rules

## Edge Cases to Test

### String-based basename extraction
```python
source_path.rstrip("/").split("/")[-1]
```
- Empty string → ""
- Root path "/" → ""
- Trailing slashes → handled correctly
- No directory separators → returns input
- Normal paths → returns basename correctly
