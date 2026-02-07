# Workflow: Cognitive Loop

The standard loop for shipping a feature from idea to merged code. This is the default workflow for most roadmap tasks.

## Sequence

```
Architect → Implementer → Test Guardian → PR Reviewer → Merge → Decision Log
    ▲                                          │
    └──────────── iterate if needed ───────────┘
```

## Phases

### 1. Architect: Validate Design

**Agent**: Architect (`/arch`)
**Input**: Feature description or task from roadmap.
**Output**: Architecture assessment with `OK TO PROCEED` or `NEEDS ADJUSTMENT`.

**What happens**:
- Verify the feature fits layer boundaries
- Check for naming collisions, dependency direction violations
- Confirm integration path exists

**Stop if**: `NEEDS ADJUSTMENT` — fix design issues before writing code.

---

### 2. Implementer: Build It

**Agent**: Implementer
**Input**: Approved design from step 1.
**Output**: Working code + passing lint + passing tests + summary + diff.

**What happens**:
- Restate task outcome and ship criteria
- Propose plan (max 6 bullets), then implement
- Run `ruff check .` and `pytest -q`

**Stop if**: Lint or tests fail — fix before proceeding.

---

### 3. Test Guardian: Verify Coverage

**Agent**: Test Guardian
**Input**: Implemented code from step 2.
**Output**: Coverage assessment with `TESTS SUFFICIENT` or `TESTS NEEDED`.

**What happens**:
- Check for missing test coverage on new/changed code
- Verify invariants are tested (token counts, boundaries, error paths)
- Flag any flaky or non-deterministic patterns

**Iterate if**: `TESTS NEEDED` — go back to Implementer to add required tests, then re-validate.

---

### 4. PR Reviewer: Final Review

**Agent**: PR Reviewer (`/pr-review`)
**Input**: Complete branch with code + tests from steps 2–3.
**Output**: Structured review with `APPROVE` or `REQUEST CHANGES`.

**What happens**:
- Autonomous review against `main`
- Check correctness, architecture, tests, integration friction
- Produce must-fix items and suggestions

**Iterate if**: `REQUEST CHANGES` — go back to Implementer to address must-fix items, then re-review. Max 2 iterations before escalating to a human.

---

### 5. Merge

**Action**: Merge PR to `main`.
**Prerequisite**: `APPROVE` from PR Reviewer + all status checks green.

---

### 6. Decision Log Update

**Action**: If the feature introduced an architectural decision (new boundary, new dependency, new pattern), append it to `rules/decision-log.md` using the `DL-###` format.

**Skip if**: The feature was a straightforward implementation with no new decisions.

## Iteration Rules

- **Max 2 review cycles** before human escalation.
- **Never skip Test Guardian** — even if code "looks fine."
- **Decision log updates are optional** but encouraged for any non-trivial choice.
- **If Architect says `NEEDS ADJUSTMENT`**, do not proceed to implementation. Fix first.
