# Workflow: [Name]

[One sentence: what scenario does this workflow handle?]

## Context

**When to use**: [Trigger conditions]
**Prerequisite**: [What must be true before starting]

## Sequence

```
[Agent 1] → [Agent 2] → [Agent 3] → [Outcome]
```

## Phases

### 1. [Phase Name]

**Agent**: [Agent name] (`/command` if applicable)
**Input**: [What this phase receives]
**Output**: [What this phase produces, including verdict]

**What happens**:
- [Step 1]
- [Step 2]

**Stop/iterate if**: [Condition that blocks progress or requires looping back]

---

### 2. [Phase Name]

**Agent**: [Agent name]
**Input**: [What this phase receives]
**Output**: [What this phase produces]

**What happens**:
- [Step 1]
- [Step 2]

**Stop/iterate if**: [Condition]

## Acceptance Criteria

- [ ] [What must be true for this workflow to be considered complete]
- [ ] [Second criterion]
- [ ] [Third criterion]

## Iteration Rules

- [Max iterations before escalation]
- [Phases that must not be skipped]
- [When to abort the workflow]
