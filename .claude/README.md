# .claude/ — AI Collaboration Layer

Cognitive infrastructure for AI-assisted development on this repository.

> **New here?** Read `agent-registry.md` first. It lists every agent and when to use it.

---

## Navigation

### Agents — WHO

Agent definitions: persona, mission, output format.

| Agent | File | Slash command |
|-------|------|---------------|
| Architect | [agents/architect.md](agents/architect.md) | `/arch` |
| PR Reviewer | [agents/pr-reviewer.md](agents/pr-reviewer.md) | `/pr-review` |
| Explainer | [agents/explainer.md](agents/explainer.md) | `/explain` |
| Implementer | [agents/implementer.md](agents/implementer.md) | — |
| Test Guardian | [agents/test-guardian.md](agents/test-guardian.md) | — |
| Refactorer | [agents/refactorer.md](agents/refactorer.md) | — |

Full details: [agent-registry.md](agent-registry.md)

### Rules — BOUNDARIES

Global constraints all agents must follow.

| Rule | File |
|------|------|
| Architecture & layer boundaries | [rules/architecture.md](rules/architecture.md) |
| Review & code quality standards | [rules/review-standards.md](rules/review-standards.md) |
| Decision log (DL-###) | [rules/decision-log.md](rules/decision-log.md) |

### Workflows — WHEN + ORDER

Multi-agent sequences for common scenarios.

| Workflow | File | Sequence |
|----------|------|----------|
| Cognitive Loop | [workflows/cognitive-loop.md](workflows/cognitive-loop.md) | Architect → Impl → Test → Review → Merge |
| Feature Development | [workflows/feature-development.md](workflows/feature-development.md) | Architect → Impl → Test → Explain → Review |
| PR Lifecycle | [workflows/pr-lifecycle.md](workflows/pr-lifecycle.md) | Explain → Review → (fix) → re-review |
| Architecture Change | [workflows/architecture-change.md](workflows/architecture-change.md) | Architect → Refactor → Test → Architect → Review |

### Playbooks — HOW

Step-by-step procedures for specific tasks.

| Playbook | File |
|----------|------|
| Architecture review | [playbooks/architecture-review.md](playbooks/architecture-review.md) |
| PR review | [playbooks/pr-review.md](playbooks/pr-review.md) |
| Code explanation | [playbooks/code-explanation.md](playbooks/code-explanation.md) |
| Implementation | [playbooks/implementation.md](playbooks/implementation.md) |
| Refactoring | [playbooks/refactoring.md](playbooks/refactoring.md) |

### Commands — SHORTCUTS

| Command | File |
|---------|------|
| `/arch` | [commands/arch.md](commands/arch.md) |
| `/explain` | [commands/explain.md](commands/explain.md) |
| `/pr-review` | [commands/pr-review.md](commands/pr-review.md) |

### Templates — SCAFFOLDS

Copy these when creating new agents, playbooks, or workflows.

| Template | File |
|----------|------|
| New agent | [templates/agent.md](templates/agent.md) |
| New playbook | [templates/playbook.md](templates/playbook.md) |
| New workflow | [templates/workflow.md](templates/workflow.md) |

---

## Adding a New Agent

1. Copy `templates/agent.md` → `agents/<name>.md`
2. Copy `templates/playbook.md` → `playbooks/<name>.md`
3. Register in `agent-registry.md`
4. Optionally create `commands/<name>.md`

## Conventions

- **Kebab-case** for all filenames: `pr-reviewer.md`, not `pr_reviewer.md`
- **One file per concern** — don't merge agent + playbook
- **Output formats are mandatory** — every agent defines its exact output structure

## Security

`settings.local.json` grants Claude Code permission to run shell commands.
Review when onboarding new team members or tightening CI.
