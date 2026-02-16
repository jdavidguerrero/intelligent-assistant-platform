---
command: pr-review
description: Invoke the PR Reviewer agent to review current branch against main.
---

Invoke the PR Reviewer agent.

Execute the review autonomously against main.
Run `git diff main...HEAD` to understand the change.
Do not ask for pasted input. Inspect the repository directly.
End with: APPROVE or REQUEST CHANGES.
