## Why

Claude-backend crew containers call `api.anthropic.com` directly. Operators running local LLMs with Anthropic-compatible APIs (litellm, OpenRouter, LM Studio, etc.) have no way to redirect that traffic — every crew is hard-wired to Anthropic's endpoint. Adding `GA_CREW_ANTHROPIC_BASE_URL` lets operators point Claude-backend crews at any Anthropic-compatible router without image changes, since Claude Code already respects the `ANTHROPIC_BASE_URL` environment variable natively.

## What Changes

- **New `GA_CREW_ANTHROPIC_BASE_URL` config var** — optional string (default: unset). When set, injected as `ANTHROPIC_BASE_URL` into Claude-backend crew containers alongside `ANTHROPIC_API_KEY`. Has no effect when `GA_CREW_ACP_BACKEND != "claude"`.
- **`transport/config.py`** — add `ga_crew_anthropic_base_url: str = ""` field and `from_env()` binding
- **`transport/server.py`** — inject `ANTHROPIC_BASE_URL` into `container_env` at launch time when set
- **`transport/lifecycle.py`** — update the `api.anthropic.com` WARNING log to mention that the warning is suppressed / the endpoint is overridden when `GA_CREW_ANTHROPIC_BASE_URL` is set
- **`config/ghostship.conf.example`** — add commented-out `GA_CREW_ANTHROPIC_BASE_URL` entry in the Claude backend section
- **`docs/configuration.md`** — document the new var

## Capabilities

### New Capabilities
_(none — this is a config extension to an existing capability)_

### Modified Capabilities

- `crew-acp-backend`: Add `GA_CREW_ANTHROPIC_BASE_URL` — when set, the transport injects `ANTHROPIC_BASE_URL` into Claude-backend crew containers, allowing traffic to be routed to an Anthropic-compatible endpoint other than `api.anthropic.com`.

## Impact

- `transport/config.py` — one new field
- `transport/server.py` — one new env injection in `launch()`
- `transport/lifecycle.py` — updated WARNING log message
- `config/ghostship.conf.example` — one new commented line in the Claude backend section
- `docs/configuration.md` — one new table row
- No image changes required
