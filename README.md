# Gumloop Python Client

A Python client and CLI for Gumloop agents, sessions, inference, tools, knowledge, and saved workflows. Use `Gumloop` or `AsyncGumloop` for new code; `GumloopClient` remains available for legacy workflow callers.

See the [client capability guide](docs/client-capabilities.md) for sync/async differences, endpoint authentication, streaming behavior, and direct versus agent-mediated features.

## CLI

Install on macOS or Linux:

```bash
curl -fsSL https://gumloop.com/cli/install.sh | sh
```

The installer is fully self-contained under `~/.gumloop` — it ships its own Python, never touches your system Python, and needs no sudo. Run `gumloop --help` to get started and update any time with:

```bash
gumloop update
```

### Import your browser sign-ins into a browser profile

Gumloop agents that use the Browser ability keep their sign-ins in a **browser profile**. Import the sites you are already signed into locally (Chrome, Brave, Edge, Chromium, Arc, Firefox on macOS or Linux) without an extension. By default every site in the local browser profile you pick comes across; you see the sites and cookie counts and confirm before anything is sent:

```bash
gumloop browser import-logins                                          # every site, into your personal default profile
gumloop browser import-logins --browser brave --exclude-domain doubleclick.net
gumloop browser import-logins --include-domain github.com --include-domain linear.app
gumloop browser import-logins --url https://mail.google.com --team <team_id> --into 'Ops inbox'   # one site
gumloop browser profiles list
```

Or, without installing anything first (set `GUMLOOP_LOGIN_URL` to import a single site, `GUMLOOP_EXCLUDE_DOMAINS` / `GUMLOOP_INCLUDE_DOMAINS` to narrow a whole-profile import):

```bash
curl -fsSL https://gumloop.com/cli/import-logins.sh | sh
```

Cookies only: local storage and IndexedDB stay on your machine, so sites that keep the session there ask the agent to sign in once, after which the agent's browser keeps it. Imported cookies are encrypted with the profile's own key before storage and are never shown back in the UI or API; sign-ins the agent picks up while running are saved back to the same profile. Rename, remove sites from, or delete profiles on the Secrets page in Gumloop.

### Sync a folder into your Brain

Mirror a local directory into a file-upload Brain source. Files are compared by name and sha256, so a re-run uploads only what changed; indexing starts on its own after each upload.

```bash
gumloop brain sync ./docs --create "Engineering docs"                 # personal source
gumloop brain sync ./docs --source <source_id> --prune                # existing source, delete remote files that are gone locally
gumloop brain sync ./runbooks --create "Runbooks" --team-id <team_id> # team source
gumloop brain sync ./policies --create "Policies" --scope organization --require-approval --approve
gumloop brain sources list
gumloop brain files list <source_id>
gumloop brain search "expense policy"
```

`--require-approval` creates the source as a draft that only estimates credits; `gumloop brain sources estimate <source_id>` shows the number and `gumloop brain sources approve <source_id>` (or `--approve`) starts indexing. Without it the source is active and indexes on the first upload.

## SDK

Agent `create`, `update`, and `attach-mcp-server` accept `--args-file`, `--args-json`, or `--args -` for full SDK configuration; explicit flags override matching JSON fields. This exposes agent metadata/settings and connector account, credential, approval, and restriction settings. `agents set-abilities` updates native abilities from the same JSON inputs. `agents knowledge-sources list|attach|detach`, `agents subagents attach|detach`, `agents triggers list|create|update|delete|webhook-url`, `agents app-rules`, `agents eval-config|set-eval-config|eval-results|eval-result`, and `agents delete` wrap the corresponding SDK operations. Trigger create/update JSON follows the SDK request shape; `{"enabled":false}` pauses a trigger. Webhook URLs contain secrets and are fetched explicitly. Agent deletion retires the agent; do not use it to pause triggers.

Agent session `create` and `send` accept `--stream`; combine with `--json` for NDJSON events, including cursors and terminal/error events. Reconnect with `gumloop sessions resume SESSION_ID --cursor LAST_STREAM_CURSOR --json` without resending a message. Human streams show text and resume cursors. `sessions create --metadata-json '{"source":"cli"}'` sets session metadata. Without `--stream`, create/send return the immediate session response and execution may continue asynchronously.

App rules can be managed with sync/async `client.agents.create_app_rule`, `update_app_rule`, and `delete_app_rule`, or `gumloop agents rules list|create|update|delete`. Create/update accept the standard JSON inputs; for example, `gumloop agents rules create AGENT_ID --args-json '{"name":"Review messages","scope":{"server_id":"slack"},"action":"tag"}'`. New rules default to disabled; update with `{"status":"enabled"}` to enable one. Rules stay scoped to their agent, require its app-rule management permission, and use OAuth or a personal API key. Pass explicit nulls in a request mapping to clear optional fields. These writes require the corresponding app-rule backend API deployment.

`gumloop chat completions create --args-file request.json --json` accepts the full SDK request shape, including conversation history, multimodal messages, tools/results, reasoning/provider options, and `image_config`. Use `--args-json` or `--args -` for inline/stdin JSON. Structured messages cannot be mixed with a prompt or message/system flags; explicit model/token/temperature/modality/schema and stream flags override the matching JSON fields. A JSON `stream` value is honored unless overridden. Human image responses display a notice; `--json` retains image data, and streaming JSON emits one chunk per line.

Answer pending tool approvals, human input, and checkpoints with `gumloop sessions approvals SESSION_ID --args-file responses.json --json` (also `--args-json` or `--args -`). Get IDs and question definitions from `sessions get SESSION_ID --json` → `session.pending_approvals`. The body is `{"approval_responses":[{"action_request_id":"request_id","action":"accept","response":{"values":{"question_name":"option_value"}}}]}`; omit `response` for ordinary approvals, or use `"action":"reject"` with an optional `reason`. Sync/async SDK clients expose `sessions.resolve_approvals` with typed requests/results; `stream_message` and `send(stream=True)` also accept approval-only continuations. Non-streaming approval responses use the dedicated method. The server validates request identity, session state, and form values before resuming execution.

Manage pending agent messages with `gumloop sessions queue list|add|edit|delete|send`. Add/edit accept `--input` or `--input-stdin -`; all support `--json`. Queue `send` immediately promotes a message and interrupts any active run. Sync and async SDK clients expose `sessions.list_queue`, `queue_message`, `edit_queued_message`, `delete_queued_message`, and `send_queued_message`; queue responses include ordered typed messages with IDs, state, and position.

Upload and attach files to an existing session with `gumloop sessions send SESSION_ID --input 'Read this file' --file report.pdf --json`. Repeat `--file` for several files. `gumloop sessions upload SESSION_ID report.pdf --json` uploads without sending a message. In Python, `client.sessions.upload_file(session_id, "report.pdf", pdf_bytes)` returns a stored file reference that can be passed to `client.sessions.send(session_id, input="Read this", attachments=[{"file_name": uploaded.file_name}])`. Both sync and async clients support this; uploads belong to that session, separately from Brain sources and workflow files.

Read your personal wiki from the terminal with `gumloop wiki query --json`, or filter a card with `--type project --entity-key launch`. The SDK provides the same query through `client.wiki.query(type="project", entity_key="launch")` on both synchronous and asynchronous clients. Queries are scoped to the authenticated user's personal wiki and retain the API's permission checks.

To use the client as a library in your own Python project:

```bash
uv add gumloop
```

## Usage

```python
from gumloop import GumloopClient

# Initialize the client
client = GumloopClient(
    api_key="your_api_key",
    user_id="your_user_id"
)

# Run a flow and wait for outputs
output = client.run_flow(
    flow_id="your_flow_id",
    inputs={
        "recipient": "example@email.com",
        "subject": "Hello",
        "body": "World"
    }
)

print(output)
```

## Authenticate with a team API key

Find IDs without leaving the terminal:

```bash
gumloop teams list --json
gumloop organizations list --json
```

Use a returned team ID with the global `--team-id` option. These commands list memberships; organization administration remains outside this command group.

Team (workspace) API keys are scoped to a single team. Pass the team's ID and
the acting member's user ID — every request is validated against that team and
only reaches resources the team owns.

```python
from gumloop import Gumloop

client = Gumloop(
    api_key="your_team_api_key",
    user_id="your_user_id",  # must be a member of the team
    team_id="your_team_id",
)

agents = client.agents.list()  # scoped to the team
```

`team_id` can also be provided via the `GUMLOOP_TEAM_ID` environment variable.

## Chat with an agent (streaming)

```python
import asyncio

from gumloop import AsyncGumloop


async def main() -> None:
    async with AsyncGumloop(access_token="your_access_token") as client:
        agents = await client.agents.list()
        agent = agents.agents[0]

        async for event in client.sessions.stream(
            agent.id,
            input="Hello, what can you do?",
        ):
            print(event)


asyncio.run(main())
```

## Route a task to the right model

Ask Gumloop Chew which of your candidate models should handle a task. Decision only — nothing runs.

```python
from gumloop import Gumloop

client = Gumloop(api_key="your_api_key", user_id="your_user_id")

decision = client.models.route(
    input="Summarize this email thread and draft a reply",
    models=["gpt-5.6-luna", "x-ai/grok-4.6", "claude-opus-5"],
)

print(decision.route.model, decision.route.lane, decision.route.fallback_models)
```

Omit `models` to route across the full Chew catalog. Each call bills one small classifier completion.

## Ask a decision model

Pass the SDK's decision request shape through the CLI using `--args-json`, `--args-file`, or `--args -` for stdin:

```bash
gumloop decisions create --args-file decision.json --json
```

```json
{"model":"typesafe/jev-1.13","state":{"message":"The screen is blank"},"questions":{"is_bug":{"type":"noul","instructions":"Is this a software defect?"}}}
```

## Put files into your Brain

```python
from gumloop import Gumloop

client = Gumloop(api_key="your_api_key", user_id="your_user_id")

source = client.brain.create_source("Engineering docs").source
upload = client.brain.upload_files(source.id, {"handbook.pdf": open("handbook.pdf", "rb").read()})

print([f.status for f in upload.files], upload.rejected)
print(client.brain.search("onboarding checklist").results[0].title)
```

Every file carries its `sha256`, so `client.brain.list_files(source.id)` is enough to diff a local folder against the source.

### Manage connected Brain sources

Once account authorization or MCP setup is complete in the Gumloop app, `create_source` also accepts `source_type`, `config`, and `credentials_to_use`. Connected sources start as drafts and require estimate approval; `require_approval=False` is rejected. The existing file-upload default remains unchanged. Source-specific configuration and credential selection follow the same rules as the app, including protected MCP plans, scripts, and allowed tools.

`get_source_configuration` requires source management permission and returns editable settings and credential selectors without private setup diagnostics. `update_source` changes settings, `browse_source` lists account nodes, `sync_source` queues work or retries setup, and `pause_source`/`resume_source` control approved sources. `list_sync_runs`, `list_source_issues`, and `list_source_children` return cursor-paginated history, issues, and indexed documents; document visibility is checked for the caller. The same methods are available on `AsyncGumloop`.

```python
settings = client.brain.get_source_configuration(source.id)
history = client.brain.list_sync_runs(source.id, page_size=20)
children = client.brain.list_source_children(source.id, page_size=100)
```

```sh
gumloop brain sources connect --args-file connected-source.json --json
gumloop brain sources configuration SOURCE_ID --json
gumloop brain sources configure SOURCE_ID --args-json '{"name":"Engineering docs"}' --json
gumloop brain sources browse google_drive --args-file browse-settings.json --json
gumloop brain sources sync SOURCE_ID --json
gumloop brain sources pause SOURCE_ID --json
gumloop brain sources resume SOURCE_ID --json
gumloop brain sources history SOURCE_ID --page-size 20 --json
gumloop brain sources issues SOURCE_ID --json
gumloop brain sources children SOURCE_ID --json
```

The JSON commands accept `--args-json`, `--args-file`, or `--args -` for stdin. Source sharing and role management remain separate from these lifecycle operations.

### Saved workflows

`Gumloop` and `AsyncGumloop` expose `workflows.list()`, `list_workbooks()`, `inputs(workflow_id)`, `start()`, `get_run()`, `cancel_run()`, and `wait()`. A workflow ID is the saved tab's `saved_item_id`, not the containing `workbook_id`. `run()` starts and waits, returning a typed run with outputs; `WorkflowExecutionError` includes the terminal run on failure or termination. Its `timeout` limits polling after startup; the initial start request uses the client's HTTP timeout. A polling timeout leaves the remote run active. Existing `GumloopClient.run_flow()` users remain supported.

```python
with Gumloop(api_key="...", user_id="...") as client:
    started = client.workflows.start("saved_item_id", {"Input": "hello"})
    result = client.workflows.wait(started.run_id, timeout=120)
    print(result.outputs)
```

Personal keys and OAuth use personal workflow storage by default; pass `project_id` for a workspace. Team keys retain their authenticated team scope. File writes with personal credentials in a workspace require project update permission. `upload_file`/`upload_files` accept bytes; `download_file`/`download_files` return bytes with a configurable size limit (64 MiB by default), with the bulk download returned as ZIP. These APIs manage existing workflow execution and files; they do not author the visual canvas.

```sh
gumloop workflows list --json
gumloop workflows workbooks --json
gumloop workflows inputs SAVED_ITEM_ID --json
gumloop workflows run SAVED_ITEM_ID --args-json '{"Input":"hello"}' --wait --timeout 120 --json
gumloop workflows status RUN_ID --json
gumloop workflows cancel RUN_ID --json
gumloop workflows upload ./input.csv --json
gumloop workflows download STORED_FILE_NAME --output ./download.csv --json
```

CLI workflow uploads validate all paths before reading contents and accept at most 200 MiB total per command, including bulk uploads.

### Browser profiles and session handoffs

Both clients expose `browser_profiles.create(name, team_id=...)`, `get(profile_id)`, `update(profile_id, name=..., is_default=True)`, `delete(profile_id)`, and `remove_site(profile_id, site)`. A method's `team_id` overrides the client's default team; without either, calls use personal scope. The `default` alias resolves only your personal default in personal scope. Profile responses contain metadata, never cookie contents or encryption keys.

```python
profile = client.browser_profiles.create("Work")
profile = client.browser_profiles.update(profile.profile_id, name="Work browser")
view = client.sessions.browser("session_id")
print(view.viewer_url)
for handoff in view.handoffs:
    print(handoff.manage_url)
```

`async_client` exposes the same methods with `await`. Browser status includes availability, the public controller identity, elapsed seconds, and authenticated Gumloop UI links. Follow the viewer or handoff link while signed in to complete a browser step; these methods do not issue browser control tokens or execute sandbox commands. Existing session approval endpoints continue to reject browser handoffs.

```sh
gumloop browser profiles create "Work" --json
gumloop browser profiles get PROFILE_ID --json
gumloop browser profiles update PROFILE_ID --name "Work browser" --json
gumloop browser profiles remove-site PROFILE_ID example.com --json
gumloop browser profiles delete PROFILE_ID --json
gumloop sessions browser SESSION_ID --json
```

### Generated file lifecycle

The sync/async `artifacts` resource supports `retrieve`, `content`, `rename`, `delete`, `list_versions`, `restore`, hosting configuration, and declared-script execution. These are generated files, separate from session input uploads. Display-name changes preserve the stored filename. Legacy generated files support soft deletion, version discovery, and downloads; VFS handles support queued, append-only restore and cannot be deleted through this API. Content and script downloads return bytes, bounded to 64 MiB by default. CLI content and script downloads stage the complete bytes before installation; replacing an existing file requires `--force` and preserves its regular read/write/execute permissions. New files respect the process umask. On volumes without hard links, installation uses an exclusive copy: other readers may see that new file while it is copied, and a failed copy removes the partial output if it still belongs to the download. Existing files are never overwritten without `--force`.

```sh
gumloop artifacts get FILE_ID --json
gumloop artifacts content FILE_ID --output ./file.bin --json
gumloop artifacts rename FILE_ID --name "Quarterly report" --json
gumloop artifacts versions FILE_ID --json
gumloop artifacts restore VFS_FILE_ID VERSION_ID --json
gumloop artifacts hosting get FILE_ID --json
gumloop artifacts hosting enable FILE_ID --alias my-report --json
gumloop artifacts hosting disable FILE_ID --json
gumloop artifacts scripts list FILE_ID --json
gumloop artifacts scripts acknowledge-integrations FILE_ID REVIEWED_CONSENT_VERSION_ID --json
gumloop artifacts scripts execute FILE_ID SCRIPT_KEY --args-json '{"payload":{"query":"example"}}' --json
```

Script execution uses the caller's current account permissions, the file's current tool policy, and ordinary execution billing. Review current declared tools, then explicitly acknowledge the returned `consent_version_id`; `version_id` independently pins content, and a changed script draft requires new consent; team keys cannot record personal consent. JSON script results may be any JSON value; `download_script` or CLI `--output` requests the script's generated binary output. Hosting is supported for stored legacy artifacts; VFS handle-backed files retain the app's hosting limitation. Hosting mutations require file sharing permission and use the same alias/domain policy as the app; the SDK does not make a private file public automatically.

### Agent voice sessions

`client.voice.start(agent_id, session_id=..., offer_sdp=..., incognito=False)` exchanges your WebRTC client's SDP offer for a typed answer, voice session ID, expiry, model, voice, and transcript timing metadata. The agent must have voice enabled. Your WebRTC client handles audio and provider data channels; the SDK and CLI exchange SDP and request session shutdown. Calls use the existing Talk authorization, session ownership, credit checks, and usage billing.

```python
with Gumloop(api_key="...", user_id="...",
             base_url="https://staging.api.gumloop.com/api/v1",
             stream_base_url="https://staging.ws.gumloop.com/api/v1") as client:
    started = client.voice.start("agent_id", session_id="session_id", offer_sdp=offer_sdp)
    # Apply started.answer_sdp to your WebRTC client.
    client.voice.end("agent_id", started.voice_session_id)
```

`AsyncGumloop` exposes the same methods with `await`. Ending a call requires the voice session's creator and current agent access. The end response acknowledges the shutdown request; the existing voice worker settles final usage. Configure `stream_base_url` explicitly for staging or custom hosts, or set `GUMLOOP_STREAM_BASE_URL` for the CLI.

```sh
export GUMLOOP_BASE_URL=https://staging.api.gumloop.com/api/v1
export GUMLOOP_STREAM_BASE_URL=https://staging.ws.gumloop.com/api/v1
gumloop voice start AGENT_ID --session SESSION_ID --offer-sdp-file ./offer.sdp --json
cat ./offer.sdp | gumloop voice start AGENT_ID --session SESSION_ID --offer-sdp-stdin - --json
gumloop voice end AGENT_ID VOICE_SESSION_ID --json
```

Pass exactly one SDP input. SDK, file and stdin offers must be nonempty UTF-8 text within 1 MiB; local read and validation failures produce structured errors with `--json` before any API request. Without `--json`, stdout contains the exact UTF-8 answer SDP bytes and the voice session ID is printed to stderr, so you can redirect the answer to a file without terminal wrapping or line-ending changes.

### Integration triggers

Use `client.agents.list_trigger_operators(agent_id)` to discover registered integration operators, parameter schemas, and required credential types available under your current policy. Create an integration trigger with the existing typed `create_trigger` method; the async client has the same methods with `await`. Supply resolved IDs/maps for dynamic parameters and explicit account IDs from connector account discovery. Catalog reads do not call the external integration. Account creation or reconnection may require interactive consent.

```python
created = client.agents.create_trigger("agent_id", type="integration", prompt="Summarize new mail",
    enabled=False, integration={"operator_name": "Gmail Reader", "parameters": {"Label": "Inbox"},
        "credentials_to_use": {"gmail_access_token": {"secret_id": "account_id", "is_personal_credential": True}}})
current = client.agents.get_trigger("agent_id", created.trigger.id)
runs = client.agents.list_trigger_runs("agent_id", created.trigger.id, page_size=20, states=["FAILED"])
stats = client.agents.get_trigger_stats("agent_id", created.trigger.id)
```

`update_trigger(..., integration=...)` replaces the operator configuration as a whole and preserves the trigger's prompt, name, continuation and enabled state unless explicitly changed. Configuration replacement requires the trigger creator; personal accounts remain bound to that creator. Workspace accounts require current workspace access. Explicit account pins must belong to the selected owner and match the required credential type; unavailable pins are rejected. Reads return public configuration and status without credentials or internal event state. Run history uses cursor pagination; stats preserve native run/poll credit accounting. Enabling or changing an active integration uses the platform's existing external subscription/polling lifecycle and billing.

```sh
gumloop agents triggers catalog AGENT_ID --json
gumloop agents triggers create AGENT_ID --args-file ./integration-trigger.json --json
gumloop agents triggers get AGENT_ID TRIGGER_ID --json
gumloop agents triggers update AGENT_ID TRIGGER_ID --args-json '{"enabled":false}' --json
gumloop agents triggers runs AGENT_ID TRIGGER_ID --limit 20 --state FAILED --json
gumloop agents triggers stats AGENT_ID TRIGGER_ID --json
```

This contract does not manage shared trigger templates or instances and does not accept raw internal event JSON. Use OAuth or a personal API key for configuration and inspection.
