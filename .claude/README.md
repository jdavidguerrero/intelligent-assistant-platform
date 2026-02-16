# .claude/ — AI Collaboration Layer

Sub-agent infrastructure for AI-assisted development. Uses the official Claude Code sub-agent standard.

## Agents

All agents live in `agents/` with YAML frontmatter. Run `/agents` to discover and manage them.

| Agent | Role | Tools | Model | maxTurns |
|-------|------|-------|-------|----------|
| `architect` | Architecture review, layer boundaries | Read, Glob, Grep, Bash | sonnet | 15 |
| `pr-reviewer` | PR review, correctness, test quality | Read, Glob, Grep, Bash | sonnet | 15 |
| `explainer` | Code explanation, understanding | Read, Glob, Grep | sonnet | 15 |
| `implementer` | Build features, ship code | Read, Glob, Grep, Bash, Edit, Write | inherit | 30 |
| `test-guardian` | Test coverage, quality enforcement | Read, Glob, Grep, Bash, Edit, Write | sonnet | 30 |
| `refactorer` | Safe structural improvements | Read, Glob, Grep, Bash, Edit, Write | inherit | 30 |

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
| `/implement` | Invoke Implementer agent |
| `/test` | Invoke Test Guardian agent |
| `/refactor` | Invoke Refactorer agent |

## Agent Memory

Persistent memory for each agent lives in `agent-memory/<name>/MEMORY.md`. Agents accumulate patterns, decisions, and project-specific knowledge across sessions.

| Agent | Memory |
|-------|--------|
| `architect` | Layer boundary patterns, review checklist |
| `pr-reviewer` | Common pitfalls, multi-round protocol |
| `test-guardian` | Invariant checklist, what NOT to test |
| `implementer` | Environment setup, lint fixes, ship checklist |
| `refactorer` | Safety protocol, naming conventions |
| `explainer` | Pipeline context, explanation patterns |

## Hooks

Configured in `settings.json`. Automated reminders during development workflow.

| Hook | Trigger | Action |
|------|---------|--------|
| `PostToolUse` | After Write/Edit | Reminder to run `/test` |
| `Stop` | After implementer/refactorer finishes | Reminder: `/test` → `/pr-review` |

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
maxTurns: <15 for read-only, 30 for write agents>
---
```

## Settings

| File | Scope | Commit? |
|------|-------|---------|
| `settings.json` | Shared team defaults (safe permissions, hooks) | Yes |
| `settings.local.json` | Personal overrides (broad permissions, paths) | No (.gitignore) |

## Workflows

Standard multi-agent sequences (defined in `CLAUDE.md`):

```
Feature:      /arch → /implement → /test → /pr-review
PR Lifecycle: /explain → /pr-review → fix → re-review
Architecture: /arch → /refactor → /test → /arch → /pr-review
```

Max 2 review cycles before human escalation.
