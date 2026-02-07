# Playbook: Architecture Review

## Goal

Keep architecture clean while shipping quickly.

## When to Use

- Before starting a new feature or module
- After completing a milestone
- When layer boundaries feel unclear
- After a large refactor

## Procedure

1. Read the repo layout and key files relevant to current work.
2. Identify boundary violations:
   - `core/` importing `db/`, `api/`, or `ingestion/`
   - Side effects in pure modules (I/O, network, timestamps)
3. Check naming collisions across layers (e.g., `Chunk` vs `ChunkRecord`).
4. Verify the integration path: load → chunk → embed → persist → search → respond.
5. Recommend only changes that reduce friction for the current roadmap phase.

## Must Flag (Blocking)

- Leaky boundaries (wrong-direction imports)
- Confusing naming collisions across layers
- No clear path to integration with the pipeline
- Un-testable design (hidden dependencies, global state)

## Nice-to-Have (Non-Blocking)

- `core/types.py` to separate pure data from DB records
- `core/text.py` for pure text normalization
- `ChunkingConfig` dataclass if parameter sprawl starts

## Anti-Patterns

- Do not expand scope beyond current roadmap phase.
- Do not propose new subsystems unless critical.
- Do not recommend changes that don't reduce near-term friction.
