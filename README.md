# Gumloop Python Client

A Python client for the Gumloop API that makes it easy to run and monitor Gumloop flows, plus the `gumloop` CLI.

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

Every file carries its `sha256`, so `client.brain.list_files(source.id)` is enough to diff a local folder against the source. Only file-upload sources can be created through the API; Notion, Drive and other connected sources are set up in the Gumloop app.

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
