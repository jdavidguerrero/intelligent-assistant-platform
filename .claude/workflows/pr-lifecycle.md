# Workflow: PR Lifecycle

End-to-end workflow for preparing, reviewing, and landing a pull request.

## Sequence

```
1. Explainer    → Understand what you're shipping
2. PR Reviewer  → Autonomous review
3. Implementer  → Address feedback (if needed)
4. PR Reviewer  → Re-review (if changes were made)
```

## Steps

### 1. Pre-PR Understanding

**Agent**: Explainer
**Playbook**: `playbooks/code-explanation.md`
**Input**: Run `git diff main...HEAD`
**Purpose**: Verify the author understands the full change before opening a PR.

**Exit criteria**: `UNDERSTOOD` — author can explain every invariant and tradeoff.

### 2. Autonomous Review

**Agent**: PR Reviewer
**Command**: `/pr-review`
**Purpose**: Catch correctness issues, boundary violations, and test gaps.

**Exit criteria**: `APPROVE` → proceed to merge.

If `REQUEST CHANGES` → continue to step 3.

### 3. Address Feedback

**Agent**: Implementer
**Playbook**: `playbooks/implementation.md`
**Purpose**: Fix blocking issues identified in the review.

**Exit criteria**: All must-fix items resolved. Lint and tests pass.

### 4. Re-Review

**Agent**: PR Reviewer
**Command**: `/pr-review`
**Purpose**: Verify fixes are correct and no new issues were introduced.

**Exit criteria**: `APPROVE`

If `REQUEST CHANGES` again → loop back to step 3. Max 2 iterations before escalating to a human.
