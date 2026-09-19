## Why

TRN-167 taught the transport to select a non-default ACP runtime per crew (`GA_CREW_ACP_BACKEND=claude`), and TRN-170 added an OAuth login path for it. KiroCrew's public build now also ships a **Codex** backend (`acp_backend="codex"`, adapter `@agentclientprotocol/codex-acp`) as a first-class selectable runtime, but ghostship cannot reach it: `_validate_acp_backend` accepts only `{"kiro", "claude"}`, no crew image carries the `codex-acp` adapter, and there is no path to supply an OpenAI credential to a crew container. Adding Codex gives operators a third model provider for their crews — parallel to the Claude work, and using the same seams TRN-167/170 already established — without any code change to the transport once shipped.

## What Changes

- **`GA_CREW_ACP_BACKEND` gains a third value `"codex"`** — the accepted set becomes `{"kiro", "claude", "codex"}`. `"codex"` writes `acp_backend: "codex"` into each new crew's config at `_patch_crew_config` time.
- **New `GA_CREW_OPENAI_API_KEY` env var** — the OpenAI API key injected as `OPENAI_API_KEY` into crew containers when the Codex backend is selected (the API-key auth path, mirroring `GA_CREW_ANTHROPIC_API_KEY`).
- **New `GA_CREW_OPENAI_BASE_URL` env var** — optional OpenAI-compatible endpoint URL injected as `OPENAI_BASE_URL` into Codex-backend crew containers, mirroring `GA_CREW_ANTHROPIC_BASE_URL`. No effect when the backend is not `codex`.
- **Codex OAuth login path** — a device/OAuth login flow parallel to `POST /login/claude`, producing a `ga-codex-auth` credential archive (a tar of `~/.codex/`, holding `auth.json`) that is injected into the crew container's `~/.codex/` at launch. Lets ChatGPT-subscription operators run Codex crews without an OpenAI API key.
- **Lazy auth enforcement at launch** — when `GA_CREW_ACP_BACKEND=codex`, `launch` requires **either** `GA_CREW_OPENAI_API_KEY` **or** a non-empty `ga-codex-auth`; if neither is present it returns `not_authenticated` with a `login_url`. Not enforced at startup (matches the TRN-170 model for Claude).
- **Opt-in image layer via `INCLUDE_CODEX_AGENT` build arg** — the spec-ops Containerfile installs `@agentclientprotocol/codex-acp` (ONE npm package: the adapter ships its own compatible Codex binary — there is no second CLI, unlike Claude) only when `INCLUDE_CODEX_AGENT=true`. Surfaced through `GA_INCLUDE_CODEX_AGENT` in config/install.
- **Network warning** — a WARNING at launch names the effective OpenAI endpoint (`api.openai.com` by default, or the configured `GA_CREW_OPENAI_BASE_URL`) as the required outbound destination for Codex crews.
- **Registry + `crews()`** — the crew's `crews.json` entry and the `crews()` MCP response carry `acp_backend: "codex"`; pre-existing entries without the field default to `kiro`.
- **Governance note** — Codex's ACP session runs under the codex-acp adapter's `agent` mode, which KiroCrew verifies is advertised as `read-only` before the first prompt; ghostship's per-call kiro approval gate does not apply, and the OS-boundary credential mask (`~/.codex/auth.json`) is the compensating control. The governance spec must document this and the ACP-v1 read-visibility gap.

## Capabilities

### New Capabilities

- `codex-auth`: The Codex/OpenAI login state machine — device/OAuth flow, `ga-codex-auth` credential storage, injection into crew containers, and logout — a parallel auth path to kiro-cli and Claude, so ChatGPT-subscription operators can run Codex crews without an API key.

### Modified Capabilities

- `crew-acp-backend`: `GA_CREW_ACP_BACKEND` accepts `"codex"` as a third value; adds Codex config resolution (`GA_CREW_OPENAI_API_KEY`, `GA_CREW_OPENAI_BASE_URL`, `GA_INCLUDE_CODEX_AGENT`), the launch-time credential requirement (API key OR `ga-codex-auth`), the `api.openai.com` network warning, and `acp_backend: "codex"` in the registry and `crews()`.
- `crew-auth`: Auth injection gains a Codex branch — when `acp_backend=codex`, skip kiro-cli auth injection and instead inject `OPENAI_API_KEY` (API-key path) or the `ga-codex-auth` archive into `~/.codex/` (OAuth path).
- `installation`: The spec-ops Containerfile and `install.sh` gain a conditional Codex layer (`@agentclientprotocol/codex-acp` via `INCLUDE_CODEX_AGENT` / `GA_INCLUDE_CODEX_AGENT`); installation docs document the new env vars and the OpenAI credential requirement.
- `crew-governance`: Documents the Codex tool-approval model — the codex-acp session is verified as `read-only` at `session/new`, ghostship's per-call approval gate is bypassed, the signed policy ceiling still holds, and the credential-dir OS mask compensates for the ACP-v1 read-visibility gap.

## Impact

- `transport/config.py` — extend `_ACP_BACKEND_VALUES` with `"codex"`; add `GA_CREW_OPENAI_API_KEY`, `GA_CREW_OPENAI_BASE_URL`, `GA_INCLUDE_CODEX_AGENT`; lazy codex-credential validation
- `transport/lifecycle.py` — `_patch_crew_config` writes `acp_backend: "codex"`; launch-time codex branch (skip kiro auth, inject `OPENAI_API_KEY`/`OPENAI_BASE_URL` or `ga-codex-auth`), endpoint warning, `acp_backend` in `crews.json`; `ga-codex-login-*` container lifecycle + `ga-codex-auth` read/write/inject helpers
- `transport/server.py` — `POST/GET /login/codex` and `POST /logout/codex` endpoints; `crews()` includes `acp_backend`
- `crews/spec-ops/Containerfile` — `INCLUDE_CODEX_AGENT` build arg installing `@agentclientprotocol/codex-acp`
- `scripts/install.sh` — resolve `GA_INCLUDE_CODEX_AGENT`, pass `--build-arg INCLUDE_CODEX_AGENT=true`
- `docs/configuration.md`, `docs/architecture.md`, `docs/auth.md`, `config/ghostship.conf.example` — document the three new env vars, the OpenAI credential/login flow, the governance gap, and the `api.openai.com` network requirement
- Crew containers require outbound HTTPS to `api.openai.com` (or `GA_CREW_OPENAI_BASE_URL`) when the Codex backend is active
