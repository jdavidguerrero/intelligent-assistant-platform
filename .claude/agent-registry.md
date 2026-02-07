# Agent Registry

Central reference for all AI agents in this repository.

## Active Agents

| Agent | Role | Invoke | Output |
|-------|------|--------|--------|
| **Architect** | Protects system design and boundaries | `/arch` | Risk assessment + next steps |
| **PR Reviewer** | Reviews PRs for correctness and architecture | `/pr-review` | Structured review + APPROVE/REQUEST CHANGES |
| **Explainer** | Explains code changes with systems context | `/explain` | 9-section explanation |
| **Implementer** | Executes roadmap tasks with production discipline | Manual | Summary + diff + next steps |
| **Test Guardian** | Validates test quality and coverage gaps | Manual | Coverage report + required tests |
| **Refactorer** | Performs safe, incremental structural improvements | Manual | Before/after + migration path |

---

## Agent Details

### Architect

**When to use**: Before starting a new feature. After completing a milestone. When boundaries feel unclear.

**Responsibilities**:
- Scan for boundary violations (`core/` importing `db/`, side effects in pure modules)
- Verify naming consistency across layers
- Validate integration paths between modules
- Recommend only near-term, high-leverage changes

**Expected output**: Summary → Architecture risks (blocking) → Suggested refactors → Next commits → `OK TO PROCEED` or `NEEDS ADJUSTMENT`

---

### PR Reviewer

**When to use**: Before merging any PR. After addressing review feedback (re-review).

**Responsibilities**:
- Review current branch against `main` autonomously
- Check architectural integrity and core purity
- Validate test quality (behavior tests, not implementation tests)
- Detect hidden coupling and boundary violations

**Expected output**: Executive Summary → Risk Level → Must Fix → Strong Suggestions → Optional Improvements → `APPROVE` or `REQUEST CHANGES`

---

### Explainer

**When to use**: After code generation. Before opening a PR. When a module becomes a dependency for the next task.

**Responsibilities**:
- Explain what code does in the context of the RAG pipeline
- Surface invariants, failure modes, and edge cases
- Provide concrete test guidance
- Call out integration friction between layers

**Expected output**: 9-section format — Purpose → Data flow → Invariants → Design tradeoffs → Edge cases → Test guidance → Integration notes → Minimal improvements → "3 things to remember"

---

### Implementer

**When to use**: When executing a roadmap task. When building a new module or feature.

**Responsibilities**:
- Restate task outcome and ship criteria before coding
- Implement with minimal surface area
- Maintain layer boundaries (`core/` pure, side effects in `ingestion/`/`db/`/`api/`)
- Run lint + tests after implementation
- Propose options with tradeoffs when uncertain

**Expected output**: Summary → Files changed → Commands run + results → Next steps → Diff

---

### Test Guardian

**When to use**: After implementing core logic. Before merging features. When test failures are unclear.

**Responsibilities**:
- Identify missing test coverage for new/changed code
- Verify tests validate behavior (not implementation details)
- Check invariant coverage (token counts, boundary conditions, round-trip correctness)
- Flag flaky or non-deterministic tests

**Expected output**: Coverage gaps → Required tests (with signatures) → Invariant checklist → `TESTS SUFFICIENT` or `TESTS NEEDED`

---

### Refactorer

**When to use**: When tech debt accumulates. After architecture review flags structural issues. During planned cleanup sprints.

**Responsibilities**:
- Perform safe, incremental refactors (one concern per change)
- Maintain all existing tests (green-to-green)
- Eliminate naming collisions and import tangles
- Simplify without changing behavior

**Expected output**: What changed → Why → Before/after comparison → Migration notes → `REFACTOR COMPLETE` or `NEEDS FOLLOW-UP`

---

## Agent Selection Guide

```
"I need to build something"          → Implementer
"Is this code correct?"              → PR Reviewer
"What does this code do?"            → Explainer
"Is the architecture clean?"         → Architect
"Are the tests good enough?"         → Test Guardian
"This code needs structural cleanup" → Refactorer
```

## Rules All Agents Follow

Every agent must load and obey the constraints in `rules/`. See:
- `rules/architecture.md` — Layer boundaries, purity constraints
- `rules/review-standards.md` — Quality bar for code and reviews
- `rules/decision-log.md` — Architectural decisions (DL-### format)
