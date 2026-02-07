# Playbook: Implementation

## Goal

Implement roadmap tasks with production-quality boundaries and discipline.

## When to Use

- When executing a roadmap task
- When building a new module, feature, or integration

## Procedure

1. **Restate the task** — Confirm the outcome and ship criteria before writing any code.
2. **Propose a plan** — Max 6 bullets. Get alignment before implementing.
3. **Implement** — Minimal surface area. Respect layer boundaries.
4. **Validate** — Run `ruff check .` and `pytest -q`. Fix issues before claiming done.
5. **Produce output** — Follow the format defined in `agents/implementer.md`.

## Layer Boundaries

- `core/` — Pure, deterministic. No DB, no network, no filesystem.
- `ingestion/` — File I/O, orchestration. Side effects allowed.
- `db/` — SQLAlchemy models, persistence.
- `api/` — FastAPI endpoints. Thin controllers.

## Rules

- Prefer typed code (Python 3.12+).
- Small commits, PR-ready.
- Add or adjust tests for any `core/` logic.
- For side effects, focus on correctness and clear error messages.
- No premature frameworks — keep it minimal.

## Anti-Patterns

- Do not handwave uncertainty — propose options with tradeoffs.
- Do not skip lint or test validation.
- Do not bundle unrelated changes in one implementation.
