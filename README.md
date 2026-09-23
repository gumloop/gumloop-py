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
