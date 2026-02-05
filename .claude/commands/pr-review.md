Invoke the PR Reviewer agent.

Load:
- .claude/bootstrap.md
- .claude/rules.md
- .claude/agents/pr_reviewer.md
- .claude/playbooks/pr_review.md
- .claude/interfaces/prompts/pr_review_prompt.md

Then execute the review autonomously against main.
Run git diff if needed.
Do not ask for pasted input.