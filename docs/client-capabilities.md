# Client capabilities

`Gumloop` and `AsyncGumloop` expose service resources with equivalent request fields. Await async methods and use `async for` on streams. Managed skill sync is the exception: `client.sync` exists only on `Gumloop`.

The CLI uses these same resources. Run `gumloop <group> <command> --help` for the command's accepted fields, and use `--json` when consuming its output from a script.

The feature parity audit adds client adapters over existing APIs and selected backend additions. New backend-dependent methods require the corresponding server deployment; installing the client alone does not make them available. Organization and team administration, membership controls, custom roles, credit caps, and organization exports remain main-platform features; read-only team and organization discovery is available.

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
| Generated file metadata, bounded content, rename, delete, versions, and sharing | `client.artifacts` | `gumloop artifacts` |
| Personal browser profile CRUD, existing listing/cookie import, and session viewer links | `client.browser_profiles`, `client.sessions.browser` | `gumloop browser`, `gumloop sessions browser` |
| Connected Brain source inspection, sync history, issues, indexed children, and sync requests | `client.brain` | `gumloop brain sources` |
| Integration trigger catalog, explicit-account creation/configuration, and run history | `client.agents` trigger methods | `gumloop agents triggers` |
| Team and organization membership discovery | `client.teams.list`, `client.organizations.list` | `gumloop teams list`, `gumloop organizations list` |
| Native WebRTC voice signaling with OAuth | `client.voice.start`, `client.voice.end` | Python SDK only |
| Managed coding-agent skills | `client.sync` (synchronous only) | `gumloop sync` |
| Bundled coding-agent instructions | Local CLI installation | `gumloop plugin install` |

## Credentials and scope

An available client method does not mean every credential type can call it. Endpoint permissions, sharing grants, account policy, plan, and model availability are enforced by the backend.

Session execution, session-file uploads, queues, approvals, decisions, personal wiki, and browser endpoints use OAuth or a personal API key. Team keys are supported only by endpoints that explicitly accept them. Passing a member's user ID with a team key does not authorize that member's personal connector accounts.

Native voice signaling requires OAuth; personal and team API keys are unsupported. New personal browser CRUD and viewer methods reject a configured `team_id`. Existing browser listing and cookie import retain their own team-selection options.

Personal API keys use `api_key` plus `user_id`. OAuth uses `access_token`. SDK environment fallback reads `GUMLOOP_ACCESS_TOKEN`, `GUMLOOP_USER_ID`, and `GUMLOOP_TEAM_ID`; `GUMLOOP_API_KEY` is a CLI variable. For an alternate backend, set both `base_url` and `stream_base_url` explicitly rather than assuming they share a host.

Connector discovery lists available tools and account selectors. Creating or reconnecting an account can still require interactive consent. Tool execution rechecks account access and can incur charges or external effects.

## Response timing and structured requests

`sessions.create()` and `sessions.send()` return the immediate session response. The agent may continue running after that response. Use `sessions.stream()` or CLI `--stream` to follow events. CLI `--stream --json` emits NDJSON; save the last `stream_cursor` and pass it to `sessions resume` after a disconnect. Resume follows the existing session without resubmitting the user message, provided its stream is still resumable. A saved cursor does not guarantee resume: a completed stream or a session the backend no longer considers resumable returns `finish_reason: "not_resumable"`. Retrieve the session to inspect its current state; do not resend the message automatically.

A pending approval or human-input request is a separate operation from sending text. Read its current request ID and response schema, then call `resolve_approvals`. The server rejects stale requests and callers without the required authority. Browser handoffs use their authenticated UI links rather than generic approval resolution.

Commands that accept `--args-file`, `--args-json`, or `--args -` use the SDK request shape. Choose one JSON source. Explicit flags override corresponding JSON fields. Nested settings and lists follow their endpoint's replacement or merge rules; inspect the current resource before updating them. An agent update's `version` is an optimistic-concurrency check, not a historical version to restore.

## Direct calls and agent tools

Chat completions are independent model calls. Agent sessions can use configured tools, maintain conversation state, request approvals, and delegate work. Support for a tool inside an agent does not imply that the SDK exposes that tool's internal runtime directly.

Text-to-image generation uses an image-capable chat model and image modalities. Use JSON output to retain generated images; human CLI output prints text. Image configuration is supplied in the structured request's `image_config`. Vision inputs to ordinary chat are supported. Reference-image editing additionally requires the backend image-input adapter and a supported image-generation model: supply inline base64 `image_url` content with image output modalities. Remote URLs and storage paths are refused by that adapter; MIME, decoded size, and model limits apply. The backend discovery update includes registered image models and callable decision-model IDs, while retaining availability and policy flags.

Personal browser CRUD manages stored profiles; `sessions.browser` returns only `session_id` and `viewer_url`. A viewer link does not guarantee an active browser. Shared administration, site removal, and browser control stay in the platform UI.

`voice.start(agent_id, session_id=..., offer_sdp=..., incognito=False)` and `voice.end(agent_id, voice_session_id)` adapt existing native voice endpoints on the configured streaming host. Supply a concrete agent ID; the `gumball` and `analytics` aliases are unsupported. The caller owns its WebRTC peer, audio tracks, offer/answer exchange, and cleanup. Voice is SDK-only, with no CLI command or new public voice API. Calls can incur charges. A known native prompt-read issue awaits a platform fix; no successful live-call verification is claimed.

Session attachments, Brain source uploads, and generated files are separate storage namespaces. An ID or filename from one does not automatically become a valid input to another. Artifact `retrieve` and `content` accept a version ID; `content` defaults to a 64 MiB maximum. Rename changes a legacy generated file's display name; VFS files cannot be renamed through this API. Delete soft-deletes a legacy generated file and does not delete VFS handles. CLI content requires an explicit output path and `--force` to replace an existing file. Version restoration, hosting, and script execution are outside this client surface.

Integration-trigger creation defaults to disabled when `enabled` is omitted; schedule and webhook defaults retain their existing behavior. Every integration activation requires explicit concrete account IDs for the operator's required account types. Legacy default-only account selections must be rebound explicitly. Replacing an active integration configuration requires an explicit enabled choice. Catalog, configuration inspection, run history, and statistics expose the existing trigger engine; permissions, billing, execution, and retries remain its responsibility.

Connected Brain operations inspect source status, sync history, issues, and indexed children. `sync_source` queues a sync for an existing ready, active connected source and returns a sync-run ID; it does not wait for indexing. Current access checks and document redaction still apply, and indexing can consume credits. Connected-source creation, configuration, provider browsing, activation, pause, and resume stay on the main platform. Existing uploaded-file source creation retains its behavior.
