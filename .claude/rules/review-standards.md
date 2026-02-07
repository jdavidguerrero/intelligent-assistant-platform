# Review Standards

Quality bar for all code and reviews in this repository.

## Review Priorities (in order)

1. **Correctness & edge cases** — Does it work? What breaks?
2. **Architecture boundaries** — Does it respect layer separation?
3. **Test quality & invariants** — Do tests validate behavior, not implementation?
4. **Readability & maintainability** — Can another engineer understand this in 60 seconds?
5. **Performance** — Only when relevant. Never premature optimization.

## Code Standards

- Prefer correctness and clarity over cleverness.
- Keep modules small and focused (one responsibility per file).
- Avoid global state and singletons.
- Docstrings required for all public functions.
- Prefer explicit over clever.
- No premature abstractions — wait for the third use case.

## Review Output Standards

- Always reference exact files and line numbers.
- If proposing refactors, keep them minimal and incremental.
- Patch snippets only when small and helpful.
- No style nitpicks unless they affect correctness or readability.

## Dependency Policy

- Any new dependency must be justified with a concrete reason.
- Prefer stdlib over third-party when the stdlib solution is adequate.
- Pin versions in `requirements.txt`.
