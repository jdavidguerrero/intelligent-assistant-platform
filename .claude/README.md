# .claude/ — AI Collaboration Layer

Sub-agent infrastructure for AI-assisted development. Uses the official Claude Code sub-agent standard.

## Agents

All agents live in `agents/` with YAML frontmatter. Run `/agents` to discover and manage them.

| Agent | Role | Tools | Model |
|-------|------|-------|-------|
| `architect` | Architecture review, layer boundaries | Read, Glob, Grep, Bash | sonnet |
| `pr-reviewer` | PR review, correctness, test quality | Read, Glob, Grep, Bash | sonnet |
| `explainer` | Code explanation, understanding | Read, Glob, Grep | sonnet |
| `implementer` | Build features, ship code | Read, Glob, Grep, Bash, Edit, Write | inherit |
| `test-guardian` | Test coverage, quality enforcement | Read, Glob, Grep, Bash, Edit, Write | sonnet |
| `refactorer` | Safe structural improvements | Read, Glob, Grep, Bash, Edit, Write | inherit |

## Rules

Auto-loaded constraints in `rules/`. All agents respect these.

| Rule | File |
|------|------|
| Architecture & layer boundaries | `rules/architecture.md` |
| Review & code quality standards | `rules/review-standards.md` |
| Decision log (DL-###) | `rules/decision-log.md` |

## Commands

| Command | Purpose |
|---------|---------|
| `/arch` | Invoke Architect agent |
| `/explain` | Invoke Explainer agent |
| `/pr-review` | Invoke PR Reviewer agent |

## Adding a New Agent

Create `agents/<name>.md` with YAML frontmatter:

```yaml
---
name: <kebab-case>
description: <when to delegate to this agent>
tools: <comma-separated tool list>
model: <sonnet | opus | haiku | inherit>
permissionMode: <plan | acceptEdits | default>
memory: project
---
```

## Security

`settings.local.json` grants Claude Code permission to run shell commands.
Review when onboarding new team members or tightening CI.
