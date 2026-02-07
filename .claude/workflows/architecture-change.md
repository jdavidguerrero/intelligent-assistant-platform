# Workflow: Architecture Change

Workflow for structural changes that affect layer boundaries, module organization, or system design.

## Sequence

```
1. Architect    → Assess the change and validate design
2. Refactorer   → Execute the structural change
3. Test Guardian → Verify nothing broke
4. Architect    → Post-change validation
5. PR Reviewer  → Final review
```

## Steps

### 1. Pre-Change Assessment

**Agent**: Architect
**Command**: `/arch`
**Purpose**: Evaluate the proposed architectural change. Identify risks, validate it fits the system.

**Exit criteria**: `OK TO PROCEED` with clear scope definition.

If `NEEDS ADJUSTMENT` → refine the proposal before continuing.

### 2. Execute Refactor

**Agent**: Refactorer
**Playbook**: `playbooks/refactoring.md`
**Purpose**: Make the structural change incrementally. One concern per change.

**Rules**:
- Green-to-green: all tests must pass before AND after.
- If touching more than 5 files, break into phases.
- No behavior changes — structural improvement only.

**Exit criteria**: `REFACTOR COMPLETE`

If `NEEDS FOLLOW-UP` → plan the follow-up as a separate change.

### 3. Test Validation

**Agent**: Test Guardian
**Purpose**: Verify all existing tests still pass and coverage is adequate.

**Exit criteria**: `TESTS SUFFICIENT`

### 4. Post-Change Architecture Scan

**Agent**: Architect
**Command**: `/arch`
**Purpose**: Verify the change actually improved the architecture. No new boundary violations.

**Exit criteria**: `OK TO PROCEED` — architecture is cleaner than before.

### 5. Final Review

**Agent**: PR Reviewer
**Command**: `/pr-review`
**Purpose**: Standard review before merge.

**Exit criteria**: `APPROVE`

## Special Rules for Architecture Changes

- Never combine architecture changes with feature work in the same PR.
- Document the "why" in the PR description — architectural changes need more context than feature PRs.
- If the change affects the dependency graph, update the architecture rules if needed.
