---
name: gumloop-cli
description: "Use when the user mentions Gumloop or a task involves running or inspecting a Gumloop agent, starting or continuing an agent session, calling an integration tool (Gmail, Slack, Linear, etc.) through Gumloop MCP, searching Company Brain knowledge, managing Gumloop skills or artifacts, or sending chat completions through Gumloop. Covers setup, authentication, and the full gumloop CLI command surface."
---

# Gumloop CLI

`gumloop` is the command line for Gumloop. Every subcommand supports `--help` (`-h`) and almost all support `--json` for machine-readable output.

## Setup

1. Check whether the CLI is installed:

```bash
gumloop --version
```

2. If missing, install it (macOS, Linux, or WSL only — never native Windows):

```bash
curl -fsSL https://gumloop.com/cli/install.sh | sh
```

The installer is self-contained under `~/.gumloop`, ships its own Python, and needs no sudo.

3. Verify authentication by running any read command:

```bash
gumloop agents list
```

If it fails with an authentication error:

- **Interactive machine**: ask the user to run `gumloop login` (OAuth browser flow, stores tokens in the OS keychain).
- **Headless/CI**: set both `GUMLOOP_API_KEY` and `GUMLOOP_USER_ID` environment variables. The user generates the API key at https://www.gumloop.com/personal/connectors (Pro plan or above) and finds their user ID at https://www.gumloop.com/settings/profile/general. Never print or log the API key.

## Rules

- Always pass `--json` when you parse output; the default human tables are not stable.
- Discover instead of guessing: list live data (`gumloop agents list`, `gumloop mcp list`) rather than assuming IDs or tool names exist.
- Run `gumloop <command> --help` before using an unfamiliar command; do not invent flags.
- Scope to a workspace with `--team-id` (or `GUMLOOP_TEAM_ID`) when the user works in a team.

## Commands

| Command | What it does |
| --- | --- |
| `gumloop login` / `logout` | Manage stored credentials |
| `gumloop agents list\|get\|versions\|export\|create\|update` | Manage agents and export agent versions |
| `gumloop sessions create\|get\|send\|cancel` | Run conversations with an agent |
| `gumloop chat completions create` | Chat completion against any supported model |
| `gumloop mcp list\|get\|tools\|call` | Explore connected MCP servers and execute their tools |
| `gumloop brain search` | Hybrid search across the org's indexed knowledge (Pro+) |
| `gumloop skills list\|create\|update\|delete\|download` | Manage agent skill files |
| `gumloop artifacts list\|download` | Fetch files produced by agents |
| `gumloop sync` | Install the org's managed skills onto this machine |
| `gumloop update` | Update the CLI itself |

Full flag reference: read [references/commands.md](references/commands.md).

## Common workflows

### Run an agent

```bash
gumloop agents list --json                                   # find the agent id
gumloop sessions create agent_abc --input "..." --json       # start; note the session id
gumloop sessions send session_abc --input "follow-up" --json
```

Long prompts: pipe them in with `--input-stdin -` instead of escaping.

### Call an integration tool (Gmail, Slack, Linear, ...)

```bash
gumloop mcp list --json                        # servers connected to this account
gumloop mcp tools gmail --json                 # tool names + schemas for one server
gumloop mcp call gmail list_emails --args-json '{"max_results": 5}' --json
```

Pass the tool's `name` (not `tool_call_id`) to `mcp call`. If a server's status is not `connected`, give the user its `auth_url` to finish connecting — you cannot complete that step yourself.

### Search company knowledge

```bash
gumloop brain search "onboarding process" --limit 5 --json
```

### One-off model call

```bash
gumloop chat completions create "prompt" -m claude-sonnet-4-5 --json
```

Structured output: `--schema-file schema.json`. Stdin input: `--message-stdin -`.

## Gotchas

- `gumloop agents update --inactive` **retires** an agent permanently (later `get`/`update` return 404). To stop autonomous runs, disable the agent's triggers in the app instead.
- `gumloop skills update` is a full replace, not a merge — pass every file the skill should keep.
- `sessions create`/`send` return the final response only; there is no token streaming in the CLI (the Python SDK's `client.sessions.stream()` has it).
- Company Brain requires the Pro plan and consumes credits per search.
- On headless Linux without a keychain, `gumloop login` refuses to run; use the environment variables above.
