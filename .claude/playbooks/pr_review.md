# Playbook: How to review a PR

1) Read PR intent (why exists).
2) Scan changed files for boundary violations.
3) Verify correctness with invariants.
4) Verify tests: do they test behavior or implementation?
5) Check naming collisions (Chunk vs DB Chunk etc.)
6) Check DX: docs, comments, errors, determinism.
7) Provide review + minimal patch suggestions.