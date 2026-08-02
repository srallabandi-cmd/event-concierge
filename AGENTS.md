# Agent instructions — Event Concierge

## Permissions

This project is configured for **full agent autonomy**. The user does not want permission prompts.

Configured in:
- `.cursor/permissions.json` — MCP + terminal allowlists, Auto-review steering
- `.cursor/sandbox.json` — allow all network in sandbox
- `.cursor/cli.json` — CLI unrestricted mode
- `.cursor/hooks.json` — auto-approve shell/MCP/tool calls
- `.cursor/rules/full-autonomy.mdc` — agent instruction rule

## Recommended IDE setting

For zero prompts in Cursor Desktop, also set:

**Settings → Agents → Approvals & Execution → Run Everything**

This is a one-time UI setting and cannot be committed to the repo.
