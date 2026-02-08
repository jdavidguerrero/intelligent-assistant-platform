# Test Guardian Memory

## Core Purity Replacements

When `core/` removes stdlib I/O imports (like `os`), replacement logic must have edge-case coverage:

- `os.path.basename(path)` → `path.rstrip("/").split("/")[-1]`
  - Test: trailing slashes, no slashes, root path, multiple trailing slashes
  - Critical invariant: empty string for `/`, not crash

## What NOT to Test

- Database schema metadata (SQLAlchemy `__table_args__`, indexes) — no runtime behavior to validate
- Trivial refactors (moving imports with identical behavior) — no new test needed if behavior unchanged

## Test Coverage Checklist for Architecture Fixes

1. Identify changed logic (not just imports/metadata)
2. Map change to existing test coverage
3. Write tests for edge cases NOT covered by existing tests
4. Always run full suite, not just new tests
5. Lint new/modified test files

## Key Invariants Validated

- Token-based chunking: `encode(chunk.text) == doc_tokens[token_start:token_end]`
- Overlap correctness: `next.token_start == current.token_end - overlap`
- Coverage: first chunk starts at 0, last ends at total_tokens
- Metadata: doc_id determinism, source_name extraction, source_path preservation
