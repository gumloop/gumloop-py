# Gumloop Python Client

A Python client and CLI for Gumloop agents, sessions, inference, tools, and knowledge. Use `Gumloop` or `AsyncGumloop` for new code; `GumloopClient` remains available for legacy workflow callers.

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

`gumloop chat completions create --args-file request.json --json` accepts the full SDK request shape, including conversation history, multimodal messages, tools/results, reasoning/provider options, and `image_config`. Use `--args-json` or `--args -` for inline/stdin JSON. Structured messages cannot be mixed with a prompt or message/system flags; explicit model/token/temperature/modality/schema and stream flags override the matching JSON fields. A JSON `stream` value is honored unless overridden. Human image responses display a notice; `--json` retains image data, and streaming JSON emits one chunk per line.

Answer pending tool approvals, human input, and checkpoints with `gumloop sessions approvals SESSION_ID --args-file responses.json --json` (also `--args-json` or `--args -`). Get IDs and question definitions from `sessions get SESSION_ID --json` → `session.pending_approvals`. The body is `{"approval_responses":[{"action_request_id":"request_id","action":"accept","response":{"values":{"question_name":"option_value"}}}]}`; omit `response` for ordinary approvals, or use `"action":"reject"` with an optional `reason`. Sync/async SDK clients expose `sessions.resolve_approvals` with typed requests/results; `stream_message` and `send(stream=True)` also accept approval-only continuations. Non-streaming approval responses use the dedicated method. The server validates request identity, session state, and form values before resuming execution.

Manage pending agent messages with `gumloop sessions queue list|add|edit|delete|send`. Add/edit accept `--input` or `--input-stdin -`; all support `--json`. Queue `send` immediately promotes a message and interrupts any active run. Sync and async SDK clients expose `sessions.list_queue`, `queue_message`, `edit_queued_message`, `delete_queued_message`, and `send_queued_message`; queue responses include ordered typed messages with IDs, state, and position.

Upload and attach files to an existing session with `gumloop sessions send SESSION_ID --input 'Read this file' --file report.pdf --json`. Repeat `--file` for several files. `gumloop sessions upload SESSION_ID report.pdf --json` uploads without sending a message. In Python, `client.sessions.upload_file(session_id, "report.pdf", pdf_bytes)` returns a stored file reference that can be passed to `client.sessions.send(session_id, input="Read this", attachments=[{"file_name": uploaded.file_name}])`. Both sync and async clients support this; uploads belong to that session, separately from Brain sources.

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

Use a returned team ID with the global `--team-id` option. These commands list memberships; organization administration remains outside this command group. Team-key `teams list` requires `--team-id` and returns only that team. `organizations list` requires a personal API key or OAuth; team keys are unsupported.

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

### Existing Company Brain source inspection and sync

Both clients expose `sync_source`, `list_sync_runs`, `list_source_issues`, and `list_source_children` for existing sources. Sync requires a ready, active connected source and acknowledges queued work; it does not create, configure, approve, or activate a connector. History, issues, and indexed children retain source and document permissions.

```sh
gumloop brain sources sync SOURCE_ID --json
gumloop brain sources history SOURCE_ID --page-size 20 --json
gumloop brain sources issues SOURCE_ID --json
gumloop brain sources children SOURCE_ID --json
```

Connected-source setup and activation remain in the app. Existing file-upload source creation is unchanged.

### Queue a report for a busy session

```python
receipt = client.sessions.send(
    "session_id",
    message="The investigation is complete.",
    delivery="queued",
    idempotency_key="job_991_report",
)
```

Queued delivery returns a storage receipt with a server-assigned `message_id`.
A running session reads it through the existing queue drain; an eligible settled
session can start another turn. Stops, pending approvals, queue order, and
concurrency limits still apply. Queued delivery supports text without streaming,
attachments, or approval responses.

`idempotency_key` is optional and accepts 1–256 visible ASCII characters without
spaces. Reuse it when retrying the same report across separate calls or job
restarts. The same key and content return the original receipt; changed content
under that key returns 409. Keys are scoped to the session and sender, and retry
protection lasts while the message remains in the queue or transcript. Deleting a
queued message removes its key reservation; stop retries when canceling it.

The SDK generates a key per call when one is absent. A separate call without an
explicit key can create a duplicate. The SDK does not automatically retry HTTP
requests. Acceptance confirms storage, not processing. Capacity refusal can leave a message
queued, and a failed dispatch can leave it in the transcript unprocessed.

### Generated file lifecycle

The sync/async `artifacts` resource adds `rename`, `delete`, and `list_versions` alongside existing listing, signed downloads, and sharing. Use `artifacts.download()` to obtain the filename, media type, size, and signed download URL, or `gumloop artifacts download` to save file bytes. Generated files are separate from session input uploads. Display-name changes preserve the stored filename and are supported only for legacy files; VFS handles return `versioned_fs_rename_unsupported`. Deletion soft-deletes legacy files; VFS handles cannot be deleted through this API.

```sh
gumloop artifacts download FILE_ID --output ./file.bin --json
gumloop artifacts rename FILE_ID --name "Quarterly report" --json
gumloop artifacts get FILE_ID --json  # existing download metadata and signed URL
gumloop artifacts versions FILE_ID --json
```

### Personal browser profiles

Both clients expose personal `browser_profiles.create(name)`, `get(profile_id)`, `update(profile_id, name=..., is_default=True)`, and `delete(profile_id)`. These personal methods ignore the global team selection. Existing profile list and cookie-import behavior is unchanged. Profile responses contain metadata, not cookie values.

```sh
gumloop browser profiles create "Research" --json
gumloop browser profiles get PROFILE_ID --json
gumloop browser profiles update PROFILE_ID --name "Research" --default --json
gumloop browser profiles delete PROFILE_ID --json
```

Personal profile management uses the authenticated user regardless of global team selection.

### Integration triggers

Use `client.agents.list_trigger_operators(agent_id)` to discover registered integration operators, parameter schemas, and required credential types available under your current policy. Integration creation defaults to disabled when `enabled` is omitted; activate only with an explicit `enabled=True`. Create an integration trigger with the existing typed `create_trigger` method; the async client has the same methods with `await`. Supply resolved IDs/maps for dynamic parameters and explicit account IDs from connector account discovery. Catalog reads do not call the external integration. Account creation or reconnection may require interactive consent.

```python
created = client.agents.create_trigger("agent_id", type="integration", prompt="Summarize new mail",
    enabled=False, integration={"operator_name": "Gmail Reader", "parameters": {"Label": "Inbox"},
        "credentials_to_use": {"gmail_access_token": {"secret_id": "account_id", "is_personal_credential": True}}})
current = client.agents.get_trigger("agent_id", created.trigger.id)
runs = client.agents.list_trigger_runs("agent_id", created.trigger.id, page_size=20, states=["FAILED"])
stats = client.agents.get_trigger_stats("agent_id", created.trigger.id)
```

`update_trigger(..., integration=...)` replaces the operator configuration as a whole and preserves the trigger's prompt, name and continuation unless explicitly changed. Replacing an active integration requires an explicit `enabled` choice. Configuration replacement requires the trigger creator; personal accounts remain bound to that creator. Workspace accounts require current workspace access. Every activation requires concrete account pins belonging to the selected owner and matching the required credential types; missing or unavailable pins are rejected. Legacy default-only rows must be explicitly rebound before activation. Reads return public configuration and status without credentials or internal event state. Run history uses cursor pagination; stats preserve native run/poll credit accounting. Enabling or changing an active integration uses the platform's existing external subscription/polling lifecycle and billing.

```sh
gumloop agents triggers catalog AGENT_ID --json
gumloop agents triggers create AGENT_ID --args-file ./integration-trigger.json --json
gumloop agents triggers get AGENT_ID TRIGGER_ID --json
gumloop agents triggers update AGENT_ID TRIGGER_ID --args-json '{"enabled":false}' --json
gumloop agents triggers runs AGENT_ID TRIGGER_ID --limit 20 --state FAILED --json
gumloop agents triggers stats AGENT_ID TRIGGER_ID --json
```

This contract does not manage shared trigger templates or instances and does not accept raw internal event JSON. Use OAuth or a personal API key for configuration and inspection.

### Agent voice sessions

`client.voice.start(agent_id, session_id=..., offer_sdp=..., incognito=False)` and `client.voice.end(agent_id, voice_session_id)` use the existing OAuth native Talk routes on the configured stream host. The agent must have voice enabled. Pass its concrete agent ID; the reserved `gumball` and `analytics` aliases are not supported by native Talk routes. Use an OAuth access token; personal and team API keys are not supported by these native routes. The Python `session_id` argument is serialized as native `interaction_id`; `is_incognito` is sent explicitly, including its default `false`. SDP must be nonempty UTF-8 text within 1 MiB. `AsyncGumloop` exposes the same methods with `await`. Ending a call requires its creator and current agent access; the worker settles final usage.

The runnable [WAV media example](examples/voice_wav.py) sends an explicit WAV source, creates the `oai-events` channel, applies the answer SDP, records received audio, and closes the call and media peer in `finally`. It never opens a microphone. Install the optional media dependency with `pip install gumloop aiortc`; it is not a core SDK dependency. Supply `GUMLOOP_ACCESS_TOKEN` through your environment, plus an existing agent and session. Executing this command starts a real call using normal Talk credits and billing; this example is not run by the test suite.

```sh
python examples/voice_wav.py --agent-id AGENT_ID --session-id SESSION_ID --stream-base-url https://staging.ws.gumloop.com/api/v1 --input ./source.wav --output ./received.wav --seconds 30
```
