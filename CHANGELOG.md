# Changelog

## v0.4.0

### New features

- **`ghostship auth login` / `ghostship auth logout` (TRN-150)** — CLI subcommands for the device auth flow. `auth login` initiates the flow, prints the URL and code, and polls until complete. `auth logout` revokes the current session. Both accept `--url` and `--api-key` flags for non-default or remote transports. No new dependencies — stdlib only (`urllib.request`).

- **`GA_DASHBOARD_DEFAULT` config flag (TRN-148)** — sets the default value of the `dashboard` parameter on `launch`. When `GA_DASHBOARD_DEFAULT=true`, every `launch()` call that omits `dashboard` gets a dashboard port allocated automatically. Explicit `True`/`False` always wins. Useful for academies where you always want dashboards without updating every call site.

- **Dispatch slot parameter (TRN-147)** — replaces the `mode` parameter with `slot: str | bool | None`. Controls which KiroCrew dashboard session a dispatched task is attached to:
  - `slot=None` — headless (no session); default when the crew has no dashboard
  - `slot="bridge"` — attach to the shared `bridge` slot; default when the crew has a dashboard
  - `slot=True` — auto-generate a unique slot name per task
  - `slot="<name>"` — attach to a named slot
  - The slot is pre-created via `POST /api/chat/slots` before dispatch (409 treated as success).

- **Auto-prewarm at launch (TRN-131)** — `_prewarm_crew()` fires at the end of `_finish_crew_setup`, sending a no-op canary dispatch to warm the KiroCrew process pool before the first real task arrives. Non-fatal — a prewarm failure is logged but does not fail the launch. `pre_warm_status` in the launch response. New env vars: `GA_PREWARM_ENABLED`, `GA_PREWARM_TTL_SECS`.

- **Docs infographics + tool docstrings (TRN-66)** — 3 new infographic PNGs (architecture, usage flow, fleet hierarchy). All 10 `server.py` MCP tool docstrings updated with workflow framing. README and docs reduced by ~30% via a targeted clarity pass.

### Fixes

- **Registry batch lookup subset match (TRN-151)** — `_find_batch_by_task_ids` previously required exact set equality, so a caller with a partial task list (lost or replaced tasks) could never resolve the batch and pickup stayed pending forever. Changed to subset match: if all provided `task_ids` are members of a batch, the batch is returned. Unit tests cover exact match, subset, superset (no match), and disjoint (no match).

- **`_ensure_crew_running` waiter race (TRN-152)** — when the leader's restart raised (memory gate, active-crew limit, gateway-not-ready), `finally` still set the Event but registry status was not reliably corrected. Waiters read stale `"running"` status and proceeded against a crew the leader had just failed to start. The leader now records an explicit success/failure flag on the Event; waiters read it and propagate the error rather than proceeding blindly.

- **`podman.py` hygiene (TRN-154)**:
  - Bare `except Exception: pass` narrowed to expected HTTP statuses (404/409) across `container_stop`, `container_remove`, `volume_create`, `volume_remove`, `secret_remove`, `network_disconnect`, `network_rm`, and worker cleanup. Real socket/permission failures now propagate or log at WARNING instead of being silently swallowed.
  - httpx2 sync and async clients are now closed via the uvicorn lifespan shutdown hook instead of module-level atexit (the event loop is gone by atexit time for async clients).
  - `container_exec` response closed via `try/finally` — httpx2 `Response` has no context manager protocol.
  - Raw sockets in `container_exec_pty_stdin` / `container_exec_stdin` wrapped in `try/finally` to prevent fd leak on header-phase raise.

### Tests

- **TLS context factory tests (TRN-153)** — new `tests/unit/test_tls.py` covering `_ssl_context_factory`: TLS disabled (no cert/key), TLS enabled with valid cert/key, TLS 1.2 minimum floor enforced, missing cert file raises.
- **`TransportSecretMiddleware` tests (TRN-153)** — passthrough when secret not configured, correct header passes, wrong header → 401, missing header → 401, constant-time compare verified.
- **`_ensure_crew_running` + recovery engine tests (TRN-152)** — new unit tests for `_crew_api_with_recovery` and `_phase0_transient_503` / `_phase1_stale_cookie` / `_phase2_dead_gateway` helpers: transient 503 retry, stale cookie refresh, dead-gateway restart, and leader-failure propagation.

### Docs

- **Docs consolidation** — 13 → 8 docs files: `caddy.md` + `dashboard-proxy.md` merged into `portal.md`; `security.md` merged into `auth.md`; `remote.md` folded into `configuration.md`; `reference.md` removed.

### httpx → httpx2 migration

`encode/httpx` went unmaintained in early 2026; Pydantic picked up stewardship under the `httpx2` package name. All 5 transport modules and all test files now use `import httpx2 as httpx`. The old `httpx` package is kept pinned in `requirements.txt` solely for `httpx-ws` until it adds `httpx2` support.

### Other

- Dashboard port range hardcoded to 1024 (was configurable at 50). `GA_DASHBOARD_PORT_RANGE_SIZE` removed as a configurable env var.

---

## v0.3.2

### Security

- **Ed25519 admiral signing (TRN-136)** — Admiral mail signing moved from a shared HMAC secret to Ed25519 asymmetric keys. The private key never leaves the transport (persisted at `DATA_DIR/secrets/<crew_id>.admiral_secret`); each crew receives only the public key, mounted as a read-only, root-owned Podman secret it cannot modify even if compromised. The `X-Admiral-Sig` header and `verify-admiral-sig` exit-code contract (0/1/2) are unchanged. **Operator action required:** existing crews must be nuked and relaunched to pick up the new signing scheme — a plain restart does not migrate a crew. See [docs/auth.md](docs/auth.md).
- **Crew proxy no longer forwards transport credentials** — the crew UI/API proxy (`_handle_crew_ui_proxy` / `_handle_crew_api_proxy`) stopped forwarding the inbound `Authorization` and `X-Transport-Token` headers down to a crew's own gateway. Crew containers share the `ga-starboard` network with `ga-transport`, so a compromised crew that captured either header could previously replay it directly against the transport's own control-plane API. Neither header is used by the crew gateway — it authenticates purely via its own `mc_token_5476` session cookie — so nothing downstream depended on them.
- **`starlette` pinned to `>=1.0.1`** — closes CVE-2024-47874 and CVE-2026-48710.

### API

- **`GET /openapi.json` (TRN-129)** — new public, unauthenticated endpoint serving an OpenAPI 3.1.0 schema generated at startup from the live route table and MCP tool registry (HTTP routes with per-route auth requirements, plus MCP tools as synthetic `mcp-tools` paths). Intended as a self-documenting source of truth for client/tooling authors. A build-time script (`scripts/generate_openapi.py`) also writes the schema to disk for CI artefact capture. Reachable through Caddy's public port as well as directly on the transport.

### Fixes

- **Stale active-crew counts (TRN-132)** — `crews()` and the `GA_MAX_ACTIVE_CREWS` limit check now cross-reference the registry against actual Podman container state instead of trusting a potentially-stale `status: "running"` field. A crew stopped outside ghostship (`podman stop`, a VM reboot, an idle-monitor stop the registry missed) no longer inflates the active count or blocks legitimate launches — the registry self-heals the stale entry to `"stopped"` immediately, no transport restart needed.

### Captain templates

- **`independent-review`** — dispatches four concurrent independent reviewers (Wraith for docs, three Banshees for security/quality/test-coverage); `change_name` is optional — when provided, scopes the review to that change; when omitted, reviews the entire codebase. Consolidates findings by severity. (`independent-review-all` is merged into this template and deleted.)
- **`sdd`** — drives one or more named OpenSpec changes through the standard Spectre → Ghost → Banshee → Reaper lifecycle; `change_name` accepts a single name or a comma-separated list for parallel multi-change execution with automatic worktree isolation and merge reconciliation. (`sdd-parallel` is merged into this template and deleted.)
- **`<change?>`** token in `transport/captain.py` — optional change-name token: substitutes the provided name when `change_name` is given, or `"entire codebase"` when omitted. Raises if mixed with required `<change>` or `<changes>` in the same template body.
- **SDD reconciliation attempts conflict resolution before escalating (TRN-140)** — in parallel multi-change `sdd` execution, the reconciliation-phase Ghost task now reads each conflicting change's specs and tasks to understand intent, resolves merge conflicts by treating them as additive where possible, and re-runs the test suite, recording every decision in the Admiral mail. It previously escalated to the Admiral on the first conflict; now it only escalates if conflicts remain unresolved or tests still fail.
- **`transport://orders` is now a summary index (TRN-135)** — returns name + one-line description per standing-order template instead of every template's full body. Use the new `transport://orders/{name}` resource for a specific template's full text. New `GA_ORDERS_DIR` env var lets operators point at a directory of custom `.md` templates that merge with (and can override) the built-in `academy/orders/` set.

### Install

- **`--client-only`** flag — skips all container infrastructure (no Podman check, no image builds, no `compose up`) and wires up just the `ghostship` CLI and agent harness integrations. Designed for machines connecting to an already-running remote transport. Use with `--url` and optionally `--api-key`.
- **Transport source hash detection** — `install.sh` now hashes the transport source tree and embeds it as a label on the built image. On subsequent installs, if the version matches but the source has changed (mid-release commits), a clean rebuild is forced automatically.

### Testing

- Full-suite test bootstrap stabilized (TRN-144) — a shared httpx stub module (`tests/unit/_stubs.py`) fixes exception-identity mismatches that caused spurious `test_recovery.py` failures under the parallel test runner.
- `tests/integration/test_uninstall_auth_preservation.sh` is now actually wired into `tests/run.sh`'s integration suite — it existed but was never executed.

---

## v0.3.0

### Breaking changes

**Re-run `./install.sh` to upgrade — in-place upgrade is not supported.**

- **`GA_PORTAL_PORT` renamed to `PORT`.** `install.sh` auto-migrates existing config files with a deprecation warning. Update your config to use `PORT` to silence it.
- **`ga-portal` (Caddy) is now mandatory.** The `GA_PORTAL_ENABLED` opt-in flag is removed — portal always runs. Any deployment previously running with `GA_PORTAL_ENABLED=false` must re-run `install.sh`.
- **`ga-net` replaced by two networks.** `ga-portside` (transport ↔ portal only) and `ga-starboard` (transport ↔ crews). Existing crew containers are migrated automatically on first startup after upgrade, but `install.sh` must be re-run to create the new networks.

### Dashboard (Caddy-backed, always on)

Crew dashboards are now proxied through `ga-portal` (Caddy) rather than per-port uvicorn threads in the transport. This is the only dashboard mode — the per-port proxy is removed.

- `launch(dashboard=True)` registers a per-crew Caddy server via the admin API and returns a `dashboard_url`. `nuke` removes it. Transport startup re-registers from `crews.json` (idempotent, no Caddy restarts).
- Every dashboard port is gated by a `gs_session` cookie. Unauthenticated requests go to `/dashboard/login`; `POST /dashboard/login` issues the cookie when `GA_API_KEY` is correct (open-access when `GA_API_KEY` is unset).
- The transport injects the `mc_token_5476` crew session cookie before forwarding to the crew gateway, resolving a 403 IP-mismatch that occurred when Caddy proxied directly.
- **TLS modes:** `off` (plain HTTP, default), `internal` (Caddy built-in CA), `tailscale` (browser-trusted `.ts.net` certs), `acme` (Let's Encrypt). Configured via `GA_PORTAL_TLS_MODE`. See [docs/caddy.md](docs/caddy.md).
- When `GA_API_KEY` is set, Caddy enforces `Authorization: Bearer` on `/mcp*` and `/files/*` at the edge before requests reach the transport.

### Network isolation

- `ga-portside` — `ga-portal` ↔ `ga-transport` only. Crew containers cannot reach `ga-portal`.
- `ga-starboard` — `ga-transport` ↔ crew containers. Crews cannot reach each other.
- `GA_TRANSPORT_SECRET` — a shared secret (auto-generated by `install.sh`, stored as Podman secret `ga-transport-secret`) gates every request from `ga-portal` to `ga-transport`. `TransportSecretMiddleware` rejects requests with a missing or wrong `X-Transport-Token` header.

### KiroCrew 0.5.0

Crew base image bumped from `0.4.0` to `0.5.0`. The `sandbox: "off"` override is patched into `config.local.json` at crew start — required for rootless Podman compatibility (KiroCrew 0.5.0's default sandbox mode fails with `EPERM` under rootless).

### Config cleanup ⚠️

Removed 6 env vars that are now hardcoded internally. No operator action needed — defaults are unchanged.

| Removed variable | Hardcoded to |
|:----------------|:-------------|
| `GA_FILE_TTL_SECS` | `300` |
| `GA_MEMORY_WAIT_SECS` | `60` |
| `KC_GATEWAY_TOKEN_TTL` | `"24h"` |
| `GA_ENFORCE_HTTPS_REDIRECT` | `False` (Caddy owns redirects) |
| `GA_CSP_ENFORCE` | `True` (always enforced) |
| `GA_PORTAL_ADMIN_URL` | `"http://ga-portal:2019"` |

### KIRO_API_KEY headless auth

Crews now support a `KIRO_API_KEY` env var for headless kiro-cli authentication, bypassing the interactive device flow. Useful for non-interactive deployments. See [docs/auth.md](docs/auth.md).

### Other improvements

- `crews()` response includes `uptime_secs` for running containers.
- Schedule monitor checks the crew gateway `/api/crons` as source of truth before firing jobs.
- Captain `stop` always updates the registry; the gateway cron call is best-effort.

## v0.2.4

### TRN-80 — Per-crew dashboard proxy
- `launch(dashboard=True)` allocates a dedicated port and returns a `dashboard_url` for the crew's browser UI (opt-in; `dashboard=False` by default)
- HTTP and WebSocket proxying to the KiroCrew SPA via per-port uvicorn daemon threads
- `POST/DELETE /crews/{id}/dashboard` REST API to attach or detach a dashboard port without nuke+relaunch
- Session cookie injection and CORS origin injection for browser authentication
- `GA_DASHBOARD_PORT_ENABLED`, `GA_DASHBOARD_PORT_RANGE_START`, `GA_DASHBOARD_PORT_RANGE_SIZE` environment variables
- Known limitation: dashboard ports are network-auth only (Tailscale/firewall); TRN-91/92 cover auth hardening

### TRN-89 — Timestamps on tool responses
- `dispatch` response includes `created_at`
- `pickup` (task-level) response includes `created_at`, `started_at`, `completed_at` (ISO 8601 UTC, `null` until reached)
- `captain status` response includes `last_checkin_at`
- Mail subjects (pickup, captain status) include `received_at` parsed from the message `Date` header

### TRN-90 — Bundle clone HEAD fix
- Fixed: `evac(bundle=True)` followed by `supply(bundle=True)` now correctly checks out the working tree when the bundle HEAD ref contains slashes (e.g. `release/0.2.4`)

### TRN-93 — Security hardening
- Admiral secret delivered via stdin instead of argv — no longer visible in `ps` or `/proc`
- `crews.json` stores an opaque sha256 identifier instead of the plaintext secret
- Container hardening: `no_new_privileges=True`, `cap_drop=[CAP_NET_RAW, CAP_SYS_ADMIN]`
- `KC_GATEWAY_TOKEN_TTL` validated on transport startup
- File-transfer audit logging

### TRN-94 — Broad mailbox skim
- `captain status` returns `agent_mail` covering all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral)
- Crew-level `pickup` (no `task_id`) returns `agent_subjects` covering all 8 mailboxes
- `pickup(agent="ghost", crew_id=...)` — new agent filter returns a single-inbox response with no task list
- `read_mail_subjects.py` updated to return `{subject, received_at}` dicts

### Fixes
- WebSocket pump: `asyncio.wait(FIRST_COMPLETED)` + cancel (replaces leaky `asyncio.gather`)
- httpx client pooling: one pooled `AsyncClient` per dashboard port (was re-created per request)
- DELETE dashboard atomicity: stop and release inside `_registry_lock`

---

## v0.2.3 and earlier

See git log for history prior to v0.2.4.
