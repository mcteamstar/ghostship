## Context

See proposal.md — Why. TRN-167 and TRN-170 established the ACP-backend seam in ghostship: `GA_CREW_ACP_BACKEND` selects the runtime, `_patch_crew_config` writes `acp_backend`, `inject_auth.py`/lifecycle branch on the backend, an opt-in image layer carries the non-kiro toolchain, and a `POST /login/<backend>` OAuth flow captures a credential archive injected at launch. This change adds a third backend, `codex`, on exactly those seams.

Backend facts confirmed against the installed KiroCrew (`kiro_crew/acp_backends.py`, `acp/client.py`, `agent_sdk/backend_install.py`, `acp_tool_gate.py`):
- Codex is a first-class selectable backend in the public baseline (`ACP_BACKEND_CODEX = "codex"`, in `BASELINE_SELECTABLE_BACKENDS`).
- The adapter is `codex-acp`, npm package `@agentclientprotocol/codex-acp`. It is **ONE component** — it ships its own compatible Codex binary, so there is no second CLI to install (unlike Claude, which needs both `claude-agent-acp` and the `claude` CLI). Resolution honours a `CODEX_ACP_BIN` override.
- Codex reads its credentials from `~/.codex/auth.json` (relocatable via `CODEX_HOME`), and accepts `OPENAI_API_KEY` for the API-key path. `OPENAI_BASE_URL` redirects it to an OpenAI-compatible endpoint.
- Governance: the codex session is verified at `session/new` to advertise `mode=read-only` before the first prompt; ghostship's per-call approval gate does not apply. The ACP-v1 read-visibility gap is compensated by an OS-boundary credential mask (`adapter_hidden_credential_dirs`) covering `~/.codex/auth.json`.

Current auth path (kiro) is kiro-cli–specific (`inject_auth.py` writes the kiro SQLite DB) and must be bypassed entirely for Codex crews, exactly as it already is for Claude.

## Goals / Non-Goals

**Goals:**
- Let operators opt into Codex via `GA_CREW_ACP_BACKEND=codex`, reusing the TRN-167/170 seams rather than adding new ones.
- Two auth paths — `OPENAI_API_KEY` (API key) and `ga-codex-auth` (OAuth, ChatGPT subscription) — with lazy launch-time enforcement.
- Keep the default image lean: the `codex-acp` adapter is opt-in at build time via `GA_INCLUDE_CODEX_AGENT`.
- Surface `acp_backend: "codex"` in `crews.json` and `crews()`; warn at launch about the `api.openai.com` egress dependency.

**Non-Goals (design-level):**
- Per-crew backend selection — backend stays transport-wide (D1 of TRN-167 still holds).
- Rotating the OpenAI credential in a running crew without relaunch.
- Closing the ACP-v1 read-visibility gap — it is compensated (credential mask), not fixed, and that is KiroCrew's boundary, not ghostship's.
- A second `codex` CLI in the image — the adapter ships its own binary.

## Decisions

### D1: Reuse the TRN-167/170 backend seam, adding `codex` as a third value

`codex` joins `{"kiro", "claude"}` in `_ACP_BACKEND_VALUES`; every branch that today reads `== "claude"` gains a parallel `== "codex"` arm rather than a new abstraction. This keeps the two non-kiro backends structurally identical, which is how KiroCrew itself models them (both in `ACP_BACKENDS_MODEL_VIA_CONFIG_OPTION`, both `SESSION_CONFIG`-routed).

**Alternative considered:** a generic backend-plugin table in the transport. Rejected — two concrete backends do not justify the indirection; a table hides the per-backend auth and image differences that are the whole point.

### D2: Single-component image layer via `INCLUDE_CODEX_AGENT`

The `codex-acp` adapter ships its own Codex binary, so the Containerfile installs exactly one pinned npm package under an `INCLUDE_CODEX_AGENT=true` build arg (default false), gated from `ghostship.conf` via `GA_INCLUDE_CODEX_AGENT` and passed by `install.sh`. This mirrors the Claude layer's opt-in shape but is simpler (one package, no `CODEX_PATH` wiring — CODEX_PATH is left exactly as the operator set it).

**Alternative considered:** always include it. Rejected for the same lean-image reason as TRN-167 D2.

### D3: `OPENAI_API_KEY` injected as an env var; `ga-codex-auth` injected as a `~/.codex/` archive

The API-key path mirrors `KIRO_API_KEY`/`ANTHROPIC_API_KEY`: `--env OPENAI_API_KEY=<value>` at container creation, sourced from `GA_CREW_OPENAI_API_KEY`. The OAuth path mirrors Claude's `ga-claude-auth`: the login flow tars the login container's `~/.codex/` into `DATA_DIR/ga-codex-auth`, and launch untars it into the crew container's `/home/kirocrew/.codex/` — the path `codex-acp` reads. API key takes precedence when both are present.

**Security note:** `OPENAI_API_KEY` is visible via `podman inspect` (same limitation as the other two keys); the container boundary is the perimeter.

### D4: Codex login runs in an ephemeral `ga-codex-login-*` container

Parallel to `ga-claude-login-*`: the login runs inside a spec-ops-image container (which carries `codex-acp` only when built with `INCLUDE_CODEX_AGENT=true`), never on the host, so the resulting `~/.codex/` is captured from a known path and the container is torn down after. `POST/GET /login/codex` and `POST /logout/codex` form the state machine (see the `codex-auth` spec).

**Alternative considered:** run the OpenAI device flow on the transport host. Rejected — the host has no `codex-acp`, and writing credentials on the host outside the login-container pattern breaks the isolation TRN-170 established.

### D5: Lazy launch-time credential validation, not startup

Following TRN-170: `GA_CREW_ACP_BACKEND=codex` with no `GA_CREW_OPENAI_API_KEY` does NOT fail at startup — it lets the operator `POST /login/codex` first. The requirement (API key OR non-empty `ga-codex-auth`) is enforced at `launch`, returning `not_authenticated` + `login_url` when neither is present.

### D6: Governance — verified read-only mode plus the credential mask, documented, not re-implemented

KiroCrew already verifies the codex session is `read-only` at `session/new` and masks `~/.codex/auth.json` at the OS boundary. Ghostship's job is to (a) not fight it — the per-call approval gate simply does not apply to a codex session — and (b) document the model in `crew-governance` and `docs/architecture.md`. The signed policy ceiling still applies at the gateway. There is no ghostship-side approval-suppression env var to inject (contrast TRN-167 D4, which needed one for Claude); Codex's read-only mode is the mechanism.

## Risks / Trade-offs

- **External network dependency** → Codex calls `api.openai.com` (or `GA_CREW_OPENAI_BASE_URL`) directly from crew containers; blocked egress fails silently at session time. Mitigation: WARNING at launch naming the effective endpoint; document in `docs/architecture.md`.
- **ACP-v1 read-visibility gap** → the sensitive-path read block cannot see reads the codex adapter performs. Mitigation is not ghostship's to build — it is KiroCrew's credential-dir OS mask; ghostship documents it and does not weaken the container's standard credential-tier confinement.
- **Image build coupling** → operators must rebuild the spec-ops image to get `codex-acp`, even with a running transport. Mitigation: document in config docs (same surprise as TRN-167).
- **Version pinning maintenance** → `@agentclientprotocol/codex-acp` is pinned; bumping needs a rebuild. Mitigation: document the bump procedure alongside the Claude package's.
- **Login-flow shape uncertainty** → the exact Codex/OpenAI login UX inside `codex-acp` (device code vs browser-based sign-in, whether a `code` is surfaced) must be confirmed against the adapter during implementation; the `codex-auth` spec allows a `code`-less `login_url` response for that reason.

## Migration Plan

1. Build the Codex-enabled image: add `GA_INCLUDE_CODEX_AGENT=true` to `ghostship.conf`, re-run `./install.sh`.
2. Set `GA_CREW_ACP_BACKEND=codex` and either `GA_CREW_OPENAI_API_KEY=<key>` or plan to `POST /login/codex`.
3. Restart the transport: `ghostship stop && ghostship start`.
4. If using OAuth: `POST /login/codex`, complete the flow, poll `GET /login/codex` until authenticated.
5. Verify: `launch` a crew and `dispatch` a trivial task; confirm it completes without stalling.

Existing kiro/claude crews are unaffected — backend selection applies to newly launched crews only. **Rollback:** set `GA_CREW_ACP_BACKEND` back to `kiro` (or `claude`) and restart; running codex crews keep functioning until nuked.

## Open Questions

- Exact Codex login UX in `@agentclientprotocol/codex-acp` (device-code vs browser sign-in, and whether a short `code` is emitted alongside the `login_url`). Deferrable: the `codex-auth` spec already permits a `code`-less response, so resolving it changes only the login-container driver, not the specs or task breakdown. Confirm against the adapter during the image/login task; escalate only if no headless-capable login path exists.
