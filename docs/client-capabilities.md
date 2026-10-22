# Client capabilities

`Gumloop` and `AsyncGumloop` expose service resources with equivalent request fields. Await async methods and use `async for` on streams. Managed skill sync is the exception: `client.sync` exists only on `Gumloop`.

The CLI uses these same resources. Run `gumloop <group> <command> --help` for the command's accepted fields, and use `--json` when consuming its output from a script.

The feature parity audit adds client support over existing staging APIs. Organization and team administration, membership controls, custom roles, credit caps, and organization exports remain main-platform features; this audit adds no SDK methods or CLI commands for them.

| Capability | Python resource | CLI entry point |
| --- | --- | --- |
| Agent configuration, attachments, subagents, abilities, evaluations | `client.agents` | `gumloop agents` |
| Read agent app restrictions | `client.agents.list_app_rules` | `gumloop agents app-rules` |
| Agent conversations and resumable event streams | `client.sessions` | `gumloop sessions` |
| Session-file inputs | `client.sessions.upload_file` and message attachments | `gumloop sessions upload`, `send --file` |
| Pending tool approvals and human input | `client.sessions.resolve_approvals` | `gumloop sessions approvals` |
| Busy-session message queue | `client.sessions` queue methods | `gumloop sessions queue` |
| Independent text and image inference | `client.chat.completions` | `gumloop chat completions create` |
| Structured decisions | `client.decisions.create` | `gumloop decisions create` |
| Model discovery and task routing | `client.models` | `gumloop models` |
| Connector tools, resources, prompts, and account discovery | `client.mcp` | `gumloop mcp` |
| Personal wiki cards | `client.wiki.query` | `gumloop wiki query` |
| Company Brain search and uploaded-file sources | `client.brain` | `gumloop brain` |
| Generated files and sharing | `client.artifacts` | `gumloop artifacts` |
| Browser profile listing and cookie import | `client.browser_profiles` | `gumloop browser profiles list`, `gumloop browser import-logins` |
| Existing saved workflow execution and file transfers | `client.workflows` | `gumloop workflows` |
| Managed coding-agent skills | `client.sync` (synchronous only) | `gumloop sync` |
| Bundled coding-agent instructions | Local CLI installation | `gumloop plugin install` |

## Credentials and scope

An available client method does not mean every credential type can call it. Endpoint permissions, sharing grants, account policy, plan, and model availability are enforced by the backend.

Session execution, session-file uploads, queues, approvals, decisions, personal wiki, and browser endpoints use OAuth or a personal API key. Team keys are supported only by endpoints that explicitly accept them. Passing a member's user ID with a team key does not authorize that member's personal connector accounts.

Personal API keys use `api_key` plus `user_id`. OAuth uses `access_token`. SDK environment fallback reads `GUMLOOP_ACCESS_TOKEN`, `GUMLOOP_USER_ID`, and `GUMLOOP_TEAM_ID`; `GUMLOOP_API_KEY` is a CLI variable. For an alternate backend, set both `base_url` and `stream_base_url` explicitly rather than assuming they share a host.

Connector discovery lists available tools and account selectors. Creating or reconnecting an account can still require interactive consent. Tool execution rechecks account access and can incur charges or external effects.

## Response timing and structured requests

`sessions.create()` and `sessions.send()` return the immediate session response. The agent may continue running after that response. Use `sessions.stream()` or CLI `--stream` to follow events. CLI `--stream --json` emits NDJSON; save the last `stream_cursor` and pass it to `sessions resume` after a disconnect. Resume follows the existing session without resubmitting the user message, provided its stream is still resumable. A saved cursor does not guarantee resume: a completed stream or a session the backend no longer considers resumable returns `finish_reason: "not_resumable"`. Retrieve the session to inspect its current state; do not resend the message automatically.

A pending approval or human-input request is a separate operation from sending text. Read its current request ID and response schema, then call `resolve_approvals`. The server rejects stale requests and callers without the required authority. Browser handoffs use their authenticated UI links rather than generic approval resolution.

Commands that accept `--args-file`, `--args-json`, or `--args -` use the SDK request shape. Choose one JSON source. Explicit flags override corresponding JSON fields. Nested settings and lists follow their endpoint's replacement or merge rules; inspect the current resource before updating them. An agent update's `version` is an optimistic-concurrency check, not a historical version to restore.

`workflows.start()` starts a saved tab. `wait()` polls an existing run; `run()` combines the two. A polling timeout leaves the remote run active, and `cancel_run()` stops it. The runnable ID is the tab's `saved_item_id`, not its containing `workbook_id`. These operations execute existing workflows rather than authoring their visual canvas.

## Direct calls and agent tools

Chat completions are independent model calls. Agent sessions can use configured tools, maintain conversation state, request approvals, and delegate work. Support for a tool inside an agent does not imply that the SDK exposes that tool's internal runtime directly.

Text-to-image generation uses an image-capable chat model and image modalities. Use JSON output to retain generated images; human CLI output prints text. Image configuration is supplied in the structured request's `image_config`. Vision inputs to ordinary chat are supported; direct reference-image editing is not implemented by staging's image-generation handler and is outside this audit's client changes.

Browser profile APIs list stored profiles and import sign-ins. Profile CRUD and browser viewer/handoff links have no matching public client endpoint in this audit. Voice settings on an agent configure its voice capability; this client does not establish live WebRTC calls. A text stream is not a voice connection.

Session attachments, Brain source uploads, generated files, and workflow files are separate storage namespaces. An ID or filename from one does not automatically become a valid input to another. Generated-file restore, hosting, and script execution are outside this audit's client changes.

Agent trigger methods support existing schedule and webhook APIs. Integration-trigger configuration and connected Brain source lifecycle require additional backend APIs and are outside this audit's client changes. Configure those features on the main platform.
