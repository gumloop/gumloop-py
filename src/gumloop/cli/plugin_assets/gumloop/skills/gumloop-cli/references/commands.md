# Gumloop CLI command reference

Condensed flag reference. `gumloop <command> --help` is always authoritative. Global flags on every command: `--team-id` (`GUMLOOP_TEAM_ID`), `--base-url` (`GUMLOOP_BASE_URL`), `--version`/`-V`, `--help`/`-h`.

## Authentication

```bash
gumloop login                          # interactive: pick OAuth (browser) or API key
gumloop login --method oauth           # OAuth; add --no-browser to print the URL instead
gumloop login --api-key gum_xxx --user-id user_abc
echo "$GUMLOOP_API_KEY" | gumloop login --api-key - --user-id user_abc   # keep key out of history
gumloop logout                         # clears keychain entries, revokes OAuth refresh token
```

Environment variables (override stored credentials for one invocation; ideal for CI):

| Variable | Purpose |
| --- | --- |
| `GUMLOOP_ACCESS_TOKEN` | OAuth access token; wins over everything else |
| `GUMLOOP_API_KEY` | Personal API key; used when no access token is set |
| `GUMLOOP_USER_ID` | Required alongside `GUMLOOP_API_KEY` |
| `GUMLOOP_TEAM_ID` | Default team scope |
| `GUMLOOP_BASE_URL` | API base URL override (staging/self-hosted) |

## Agents

```bash
gumloop agents list [--search q] [--limit n] [--cursor c] [--json]
gumloop agents get <agent_id> [--json]
gumloop agents versions <agent_id> [--limit n] [--cursor c] [--json]
gumloop agents export <agent_id> <version_id> [-o file.json]
gumloop agents create --name NAME --model MODEL [--description d]
    [--system-prompt s | --system-prompt-file f]
    [--tools-json '[...]' | --tools-file f] [--json]
gumloop agents update <agent_id> [same flags as create] [--is-active | --inactive]
```

`--model` accepts `auto` or a slug like `anthropic/claude-sonnet-4`. To learn the tool-config shape, run `gumloop agents get <id> --json` on an existing agent and copy its `tools` array. `--inactive` retires the agent irreversibly.

## Sessions

```bash
gumloop sessions create <agent_id> [--input text | --input-stdin -] [--session-id id] [--json]
gumloop sessions get <session_id> [--json]          # --json returns the full transcript
gumloop sessions send <session_id> [--input text | --input-stdin -] [--json]
gumloop sessions cancel <session_id>
```

## Chat completions

```bash
gumloop chat completions create "prompt" -m MODEL
    [-s "system msg"]... [--message-stdin -]
    [--max-completion-tokens n] [--temperature t]
    [--modality image --modality text]
    [--schema-file f.json] [--schema-name name]
    [--stream | --no-stream] [--json]
```

Streams to TTYs by default, buffers when piped. `--stream --json` emits ndjson (one chunk per line).

## MCP servers

```bash
gumloop mcp list [--json]                       # SERVER_ID, STATUS, TOOLS, AUTH_URL
gumloop mcp get <server_id> [--json]
gumloop mcp tools <server_id> [--json]          # includes input schemas with --json
gumloop mcp call <server_id> <tool_name>
    (--args-json '{...}' | --args-file f.json | --args -)
    [--ref tag] [--json]
gumloop mcp resources <server_id> [--json]
gumloop mcp resource <server_id> --uri URI [--json]
gumloop mcp prompts <server_id> [--json]
gumloop mcp prompt <server_id> <prompt_name> [--json]
```

## Company Brain

```bash
gumloop brain search "query" [--limit 1-50] [--source notion]... [--json]
```

Sources: `notion`, `google_drive`, `slack`, `github`, `confluence`, `direct_file_uploads`, `gumloop_artifacts`.

## Skills

```bash
gumloop skills list [--search q] [--server id] [--limit n] [--cursor c] [--json]
gumloop skills create <file>... [--json]
gumloop skills update <skill_id> <file>... [--json]        # full replace of all files
gumloop skills delete <skill_id> [--json]
gumloop skills download <skill_id> [-o path|-] [--version-id v] [--json]
```

## Artifacts

```bash
gumloop artifacts list <agent_id> [--session id] [--limit n] [--cursor c] [--json]
gumloop artifacts download <artifact_id> [-o path|-] [--version-id v] [--json]
```

## Skill sync

```bash
gumloop sync                          # enroll persistent sync (macOS) of org-managed skills
gumloop sync --once --non-interactive # one-shot sync; requires GUMLOOP_API_KEY + GUMLOOP_USER_ID
```

## Maintenance

```bash
gumloop update                        # update the CLI in place
gumloop plugin install gumloop        # install this skill into detected agent skill directories
```
