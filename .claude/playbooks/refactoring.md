# Playbook: Refactoring

## Goal

Perform safe, incremental structural improvements without changing behavior.

## When to Use

- When tech debt accumulates beyond the comfort threshold
- After architecture review flags structural issues
- During planned cleanup sprints
- When naming collisions or import tangles need resolution

## Procedure

1. **Identify the problem** — What specific structural issue are you fixing?
2. **Verify tests pass** — Run `pytest -q` before any changes. Green baseline required.
3. **Make one change** — One concern per refactor. Never bundle unrelated changes.
4. **Run tests again** — Must stay green. If tests break, the refactor introduced a regression.
5. **Verify imports** — Check that dependency direction is correct after the change.
6. **Produce output** — Follow the format defined in `agents/refactorer.md`.

## Scope Rules

- If a refactor touches more than 5 files, break it into phases.
- Prefer renaming and reorganizing over rewriting.
- Remove dead code only when certain it is unused.
- No premature abstractions.

## Common Targets

- Naming collisions between `core/` types and `db/` models
- Import cycles or wrong-direction dependencies
- God modules with too many responsibilities
- Duplicated logic (3+ occurrences)
- Parameter sprawl in function signatures

## Anti-Patterns

- Do not refactor and add features in the same change.
- Do not create helpers or abstractions for one-time operations.
- Do not change behavior — this is structural improvement only.
