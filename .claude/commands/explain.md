---
command: explain
description: Explain selected code or recent changes using Explainer agent.
---

Load:
- .claude/rules/architecture.md
- .claude/rules/review-standards.md
- .claude/agents/explainer.md
- .claude/playbooks/code-explanation.md

If $ARGUMENTS is provided, explain that target (file, function, or module).
Otherwise, run `git diff main...HEAD` and explain the diff.

Use the exact 9-section output format defined in the agent definition.
End with: UNDERSTOOD or NEEDS REVIEW.



