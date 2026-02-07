# Workflow: Feature Development

End-to-end workflow for implementing a new feature or module.

## Sequence

```
1. Architect    → Validate design fits the system
2. Implementer  → Build the feature
3. Test Guardian → Verify test coverage
4. Explainer   → Document understanding
5. PR Reviewer  → Final review before merge
```

## Steps

### 1. Architecture Check

**Agent**: Architect
**Command**: `/arch`
**Purpose**: Verify the proposed feature respects layer boundaries and fits the integration path.

**Exit criteria**: `OK TO PROCEED`

If `NEEDS ADJUSTMENT` → resolve issues before continuing.

### 2. Implementation

**Agent**: Implementer
**Playbook**: `playbooks/implementation.md`
**Purpose**: Build the feature with production discipline.

**Exit criteria**: All lint and tests pass. Output includes summary + diff.

### 3. Test Validation

**Agent**: Test Guardian
**Purpose**: Verify new code has adequate test coverage and invariants are tested.

**Exit criteria**: `TESTS SUFFICIENT`

If `TESTS NEEDED` → implement required tests before continuing.

### 4. Explanation

**Agent**: Explainer
**Playbook**: `playbooks/code-explanation.md`
**Purpose**: Build understanding of the new code for the author and future readers.

**Exit criteria**: `UNDERSTOOD`

### 5. PR Review

**Agent**: PR Reviewer
**Command**: `/pr-review`
**Purpose**: Final autonomous review before merge.

**Exit criteria**: `APPROVE`

If `REQUEST CHANGES` → address feedback and re-run from step 2.
