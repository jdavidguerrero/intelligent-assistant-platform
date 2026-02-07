Invoke the PR Reviewer agent.

Load:
- .claude/rules/architecture.md
- .claude/rules/review-standards.md
- .claude/agents/pr-reviewer.md
- .claude/playbooks/pr-review.md

Execute the review autonomously against main.
Run `git diff main...HEAD` to understand the change.
Do not ask for pasted input. Inspect the repository directly.
