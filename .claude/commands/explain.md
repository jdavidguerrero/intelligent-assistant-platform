---
command: explain
description: Explain selected code or recent changes using Explainer agent.
---

Invoke the Explainer agent.

If $ARGUMENTS is provided, explain that target (file, function, or module).
Otherwise, run `git diff main...HEAD` and explain the diff.

Use the exact 9-section output format defined in the explainer agent.
End with: UNDERSTOOD or NEEDS REVIEW.
