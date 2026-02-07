# Playbook: Code Explanation

## Goal

Build deep understanding of code changes with a systems-builder mindset.

## When to Use

- After Claude Code generates code
- Before opening a PR (to verify understanding)
- After reviewing PR feedback (to internalize fixes)
- When a module becomes a dependency for the next task

## Input Options

Choose one:

**A) File or module**
- "Explain `core/chunking.py`"
- "Explain `tests/test_chunking.py`"

**B) Diff**
- "Explain the current diff against main"
- Or provide a specific diff snippet

**C) Function or class**
- "Explain `chunk_text()` and its invariants"
- "Explain the `Chunk` dataclass and its metadata fields"

## Procedure

1. Identify the target code (file, diff, or function).
2. Read the code directly — do not guess or paraphrase from memory.
3. Produce the 9-section explanation defined in `agents/explainer.md`.
4. Verify the explanation meets the quality bar below.

## Quality Bar

- Must mention where the code sits in the RAG pipeline.
- Must explicitly list invariants and failure modes.
- Must produce concrete test guidance.
- Must respect `core/` purity boundaries.

## Common Pitfalls to Catch

- Hidden I/O in `core/` (file reads, env vars, time without control)
- Non-deterministic `doc_id` behavior
- Chunk / DB model naming collisions
- Overlap/stride bugs (tiny final chunks, repeated coverage, missing coverage)
- Tokenization mismatch (decode/encode not round-tripping)
