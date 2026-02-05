# .claude/ Directory Structure

This directory contains configuration and prompts for Claude Code AI assistant.

## Structure

```
.claude/
├── README.md          # This file
├── bootstrap.md       # Entry point - Claude reads this first
├── rules.md           # Repository-specific coding rules
├── settings.local.json # Local Claude Code settings
├── agents/            # Agent definitions (personas, capabilities)
├── playbooks/         # Step-by-step workflows for common tasks
└── interfaces/        # Reusable prompts for invoking agents
    └── prompts/       # Prompt templates
```

## How It Works

1. **bootstrap.md** - Entry point that tells Claude where to find context
2. **rules.md** - Coding standards and constraints for this repo
3. **agents/** - Define specialized agent behaviors (e.g., PR reviewer)
4. **playbooks/** - Procedural guides for multi-step tasks
5. **interfaces/prompts/** - Reusable prompt templates for invoking agents

## Adding New Agents

1. Create agent definition in `agents/<agent_name>.md`
2. Create invocation prompt in `interfaces/prompts/<agent_name>_prompt.md`
3. Optionally create playbook in `playbooks/<task>.md`

## Security Note

`settings.local.json` contains permission settings for Claude Code.
Review these settings periodically to ensure they match your security requirements.
