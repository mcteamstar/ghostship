## 1. Image Layer — Codex Toolchain

- [ ] 1.1 Add `INCLUDE_CODEX_AGENT` build arg (default `false`) to `crews/spec-ops/Containerfile`; when `true`, install `@agentclientprotocol/codex-acp` at a pinned version (confirm exact latest version from npm before pinning). Add a comment noting it is ONE package (the adapter ships its own Codex binary — no separate `codex` CLI)
- [ ] 1.2 Confirm the `codex-acp` login/headless behaviour by reading the package docs/source: how login is initiated inside a container, where the credential lands (`~/.codex/auth.json` via `CODEX_HOME`), and whether a device code is surfaced; record findings in a Containerfile comment
- [ ] 1.3 Add `GA_INCLUDE_CODEX_AGENT` resolution to `scripts/install.sh`; pass `--build-arg INCLUDE_CODEX_AGENT=true` to the spec-ops image build when set

## 2. Transport Config

- [ ] 2.1 Extend `_ACP_BACKEND_VALUES` in `transport/config.py` to `{"kiro", "claude", "codex"}`; ensure `_validate_acp_backend` accepts `"codex"` and still rejects unknown values at startup
- [ ] 2.2 Add `GA_CREW_OPENAI_API_KEY` to `transport/config.py` (string, default empty)
- [ ] 2.3 Add `GA_CREW_OPENAI_BASE_URL` to `transport/config.py` (string, default empty; stripped)
- [ ] 2.4 Add `GA_INCLUDE_CODEX_AGENT` to `transport/config.py` (boolean, default `false`)
- [ ] 2.5 Extend the lazy credential validation so that `GA_CREW_ACP_BACKEND=codex` with neither `GA_CREW_OPENAI_API_KEY` nor `ga-codex-auth` does NOT fail at startup (validation deferred to launch, matching the TRN-170 Claude model)

## 3. Crew Lifecycle — Config, Auth, Injection

- [ ] 3.1 In `_patch_crew_config`, write `acp_backend: "codex"` into the crew config when `GA_CREW_ACP_BACKEND=codex`
- [ ] 3.2 Add a Codex branch to the launch auth path: when `GA_CREW_ACP_BACKEND=codex`, skip all kiro-cli auth injection (no device flow, no `ga-kiro-auth`, no `KIRO_API_KEY`)
- [ ] 3.3 In the Codex branch, resolve the credential in order: if `GA_CREW_OPENAI_API_KEY` is set, inject it as `OPENAI_API_KEY` env var; else if `ga-codex-auth` exists and is non-empty, untar it into the crew container's `/home/kirocrew/.codex/`; else return `not_authenticated` with a `login_url`
- [ ] 3.4 Inject `OPENAI_BASE_URL` from `GA_CREW_OPENAI_BASE_URL` into the crew container only when `GA_CREW_ACP_BACKEND=codex` and the value is set
- [ ] 3.5 Emit a WARNING-level log at `launch` when `GA_CREW_ACP_BACKEND=codex`, naming the effective endpoint (`api.openai.com` by default, or `GA_CREW_OPENAI_BASE_URL` when set) as the required outbound destination
- [ ] 3.6 Fail `launch` (or the Codex login flow) with an actionable error naming `GA_INCLUDE_CODEX_AGENT=true` when the spec-ops image lacks the `codex-acp` adapter

## 4. Codex Login State Machine

- [ ] 4.1 Add `_codex_auth_file_path`, `_codex_auth_exists`, `_write_codex_auth_file`, `_inject_codex_auth` helpers (parallel to the `_claude_*` helpers) for the `ga-codex-auth` tar of `~/.codex/`
- [ ] 4.2 Add `_start_codex_login_container` / `_nuke_codex_login_container` (ephemeral `ga-codex-login-<token>`, spec-ops image), and `_initiate_codex_login` / `_poll_codex_login_container` driving the codex-acp login and capturing `~/.codex/` on completion
- [ ] 4.3 Add `POST /login/codex`, `GET /login/codex`, `POST /logout/codex` endpoints to `transport/server.py` following the `/login/claude` pattern (409s for already-authenticated / flow-in-progress; reject when `GA_CREW_ACP_BACKEND != "codex"`)
- [ ] 4.4 Register the codex login helpers in `transport/server.py`'s lifecycle imports and add the `_codex_login_pending` state + lock in `transport/lifecycle.py`

## 5. Registry and API

- [ ] 5.1 Record the resolved `acp_backend` (`"codex"` when selected) in the crew's `crews.json` entry at launch time
- [ ] 5.2 Confirm the `crews()` MCP tool response includes `acp_backend` per crew (already added in TRN-167) and reports `"codex"` for codex crews; pre-TRN-167 entries still default to `kiro`

## 6. Docs and Config

- [ ] 6.1 Add `GA_CREW_ACP_BACKEND=codex`, `GA_CREW_OPENAI_API_KEY`, `GA_CREW_OPENAI_BASE_URL`, and `GA_INCLUDE_CODEX_AGENT` to `docs/configuration.md` with defaults, valid values, and dependency notes
- [ ] 6.2 Add commented-out entries for all four to `config/ghostship.conf.example`
- [ ] 6.3 Document the Codex login/logout flow (`POST/GET /login/codex`, `POST /logout/codex`) in `docs/auth.md` alongside the Claude flow
- [ ] 6.4 Add a `docs/architecture.md` note: Codex crews bypass ghostship's per-call approval gate, run under a verified read-only ACP mode, remain under the signed policy ceiling, and rely on the credential-dir OS mask for the ACP-v1 read-visibility gap
- [ ] 6.5 Add a `docs/architecture.md` note documenting the `api.openai.com` (or `GA_CREW_OPENAI_BASE_URL`) external network requirement for Codex crews

## 7. Tests

- [ ] 7.1 Unit test: `GA_CREW_ACP_BACKEND=codex` is accepted; an unknown value still errors at startup; `codex` with no credential does NOT error at startup
- [ ] 7.2 Unit test: `_patch_crew_config` writes `acp_backend: "codex"` when the Codex backend is selected
- [ ] 7.3 Unit test: kiro auth injection is skipped and `OPENAI_API_KEY` is injected when `GA_CREW_ACP_BACKEND=codex` with `GA_CREW_OPENAI_API_KEY` set
- [ ] 7.4 Unit test: with no API key, `ga-codex-auth` present → OAuth archive injected into `~/.codex/`; neither present → `launch` returns `not_authenticated` with a `login_url`
- [ ] 7.5 Unit test: `OPENAI_BASE_URL` is injected only for codex crews when set, and not for kiro/claude crews; launch WARNING names the effective endpoint
- [ ] 7.6 Unit test: `crews()` reports `acp_backend: "codex"` for a codex crew
- [ ] 7.7 Unit test: the codex login state machine — `POST /login/codex` 200/409 transitions, `GET /login/codex` pending→authenticated writing `ga-codex-auth`, `POST /logout/codex` clears it, and `POST /login/codex` rejected when backend is not codex
