# Ghostship v0.6.0 Release Notes

## Overview

v0.6.0 adds three new agent backends (Claude Code, Codex, and Claude OAuth), restores
the Captain autopilot for kiro-backend crews, fixes the dashboard WebSocket connection,
simplifies how tasks attach to dashboard sessions, and hardens dashboard authentication.
Two breaking changes require action before upgrading.

---

## Breaking Changes

### 1. `GA_AGENT_BACKENDS` replaces `GA_INCLUDE_CLAUDE_AGENT` and `GA_INCLUDE_CODEX_AGENT`

The old per-backend boolean flags are removed. If either is set (to any value, including
`false`), the transport and `install.sh` refuse to start and tell you what to change.

**Migrate:**

| Old config | New config |
|:-----------|:-----------|
| `GA_INCLUDE_CLAUDE_AGENT=true` | `GA_AGENT_BACKENDS=claude` |
| `GA_INCLUDE_CODEX_AGENT=true` | `GA_AGENT_BACKENDS=codex` |
| Both set | `GA_AGENT_BACKENDS=claude,codex` |

Kiro is always enabled and does not need to be listed. Re-run `./install.sh` after
updating your config — the transport does not pick up backend changes from a restart
alone because the crew image must be rebuilt.

### 2. Explicit `prewarm` tool and REST endpoint removed

`POST /crews/{id}/prewarm` now returns 404. Any caller using `prewarm(crew_id=...)` will
receive a tool-not-found error.

Warming still happens: when `GA_PREWARM_ENABLED=true`, it runs automatically as a
background side-effect of `supply` and `schedule`. The default remains `false`, so on
a standard install nothing changes in practice.

---

## New: Three Additional Agent Backends

You can now run crews powered by Claude Code, Codex, or the standard kiro-cli agent.
The default backend is still `kiro`.

### Claude Code backend

Crew containers can use Claude Code as the underlying agent runtime.

**Enable:**
```bash
# ghostship.conf
GA_AGENT_BACKENDS=claude
GA_CREW_ACP_BACKEND=claude   # make it the default for new crews
```

**Authenticate** — pick one:
- API key: set `GA_CREW_ANTHROPIC_API_KEY` in `ghostship.conf`
- OAuth (Pro/Max subscription): `POST /login/claude` → approve in browser →
  `POST /login/claude/code` with the pasted code → `GET /login/claude` until
  `"complete"`. Re-authenticate with `POST /logout/claude` then `POST /login/claude`.

**Custom endpoint:** `GA_CREW_ANTHROPIC_BASE_URL` lets you point Claude-backend crews
at a local LLM proxy (litellm, OpenRouter, etc.) without rebuilding the image.

**Note:** Claude-backend crews require outbound HTTPS to `api.anthropic.com` (or your
custom `GA_CREW_ANTHROPIC_BASE_URL`). The transport logs a warning on every `launch()`
when the Claude backend is selected.

**Known limitation:** Claude OAuth tokens expire after roughly eight hours. The first
crew to reach that point refreshes the token inside its own container; other running
crews may then fail with "OAuth session expired." Workaround: `POST /logout/claude`
then `POST /login/claude`, or use `GA_CREW_ANTHROPIC_API_KEY` instead.

### Codex backend

Crew containers can use the Codex ACP adapter as the agent runtime.

**Enable:**
```bash
# ghostship.conf
GA_AGENT_BACKENDS=codex
GA_CREW_ACP_BACKEND=codex
```

**Authenticate** — pick one:
- API key: set `GA_CREW_OPENAI_API_KEY`
- OAuth (ChatGPT subscription): `POST /login/codex` → approve in browser →
  `GET /login/codex` until `"complete"`.

Logout is idempotent: `POST /logout/codex` returns 200 even when already logged out.

**Custom endpoint:** `GA_CREW_OPENAI_BASE_URL` redirects Codex traffic to any
OpenAI-compatible endpoint.

### Claude OAuth (Pro/Max subscription path)

The OAuth login flow (`POST /login/claude` + code submission + poll) lets Claude Pro
and Max subscribers run Claude-backend crews without a pay-per-token API key.
See [docs/auth.md](auth.md#claude-oauth-login-trn-170) for the full flow.

---

## Captain Autopilot Restored

The KiroCrew 0.7.0 security update (attested session identities) broke the full Captain
workflow — headless Raven tasks had no session identity and `/api/spawn` refused them.

v0.6.0 fixes this end to end for kiro-backend crews:

- **Persona enrollment** — at crew launch, the transport now writes a `config.agents`
  section for all six personas and calls `POST /api/members/{slug}/thread` for each.
  This creates a DM binding and an attested member session identity per persona.
  Enrollment happens automatically — no operator action needed.
- **Member-based dispatch** — when personas are enrolled, `dispatch()` routes each
  task into its attested `member-<slug>` session. The response shows the clean agent
  name (e.g. `"ghost"`), not `"member-ghost"`. Sessions are visible in the dashboard.
- **Raven** sends `X-Session-Key: $KIRO_SESSION_ID` when spawning other personas,
  satisfying the attestation requirement.

**Known limitation:** Captain autopilot does not work on Claude or Codex backend crews.
Raven cannot read the crew gateway's local IPC secret that the `sdd` and
`independent-review` templates need. Use manual dispatch (`dispatch`, `pickup`, `steer`)
for non-kiro crews until this is fixed.

---

## Dashboard Improvements

### WebSocket connection fixed

Two bugs prevented the KiroCrew dashboard's live task streaming from working through
the Caddy proxy:

- WebSocket upgrade requests were hitting Caddy's `forward_auth` gate and being
  rejected with 401. Caddy now emits a separate WS upgrade route (no auth check)
  alongside the standard HTTP route (auth required) for each crew.
- The transport was sending the wrong `Origin` header for WS connections, causing the
  gateway to refuse them. Both issues are fixed; `101 Switching Protocols` is now reliable.

### Login page redesigned

`GET /dashboard/login` has a new look aligned with Ghostship's visual identity:
purple primary button, floating ghost emoji, show/hide toggle on the API key field,
shake animation on failed login, and a wider card. A backslash in the `next` redirect
parameter can no longer redirect off-site.

### Bearer auth removed from crew UI paths

Dashboard ports (`/crews/*/ui`, WebSocket) no longer accept or require a Bearer token.
The `gs_session` cookie issued by `/dashboard/login` is the sole auth gate for
dashboard access. This simplifies browser-based use — no header injection needed.

---

## Dispatch Slot Model Simplified

`dispatch()` now has two slot modes instead of four:

| Mode | Behaviour |
|:-----|:----------|
| `slot=None` (default) | Enrolled personas route into their attested member DM slot — visible in the dashboard, able to spawn downstream tasks. Unenrolled agents dispatch headless. |
| `slot=False` | Explicit headless. No session is created, saving ~250 MB RSS per dispatch. |

`slot=True`, `slot="bridge"`, and named slots are removed. They were not attested
(breaking downstream spawning) and offered no advantage now that member slots provide
browser visibility automatically. The bridge fallback for unenrolled agents on dashboard
crews is also gone — unenrolled agents always dispatch headless.

---

## Base Image Upgrade (KiroCrew 0.6.0 → 0.8.0)

The crew base image is now `ghcr.io/kirodotdev/kirocrew:0.8.0`. Changes required by the
upgrade are handled automatically by `install.sh` and the transport:

- kiro-cli DB schema updated for kiro-cli 2.24.0 (6 migration rows, `state.value`
  changed from `BLOB` to `TEXT`, three removed tables).
- Transport/Caddy readiness timeout increased to 90s for remote deployments.
- `launch` now polls the auth DB when login is pending — no longer requires
  `GET /login` to unblock the wait loop.

---

## Notable Fixes

- **Logout reached Caddy, not the transport.** `POST /logout/claude` and
  `POST /logout/codex` were answered by Caddy with an empty 200. Now properly proxied.
- **Codex login accepted any credential file.** Any non-empty file under `~/.codex/`
  counted as a completed login. Now requires a non-empty `auth.json`.
- **Login reported success after a failed credential write.** Failed writes now return
  500 and keep the session retryable.
- **`compose.yml` world-readable.** Model API keys in `compose.yml` are now written
  with mode 600.
- **Idle reaper:** one failing crew no longer ends idle reaping for the whole process.
- **`install.sh`:** flags without values now error instead of exiting silently; unknown
  `GA_PORTAL_TLS_MODE` values fail fast; a line break in `GA_AGENT_BACKENDS` is rejected.
- **Config:** `nan` and `inf` are rejected for numeric settings.
- **Presigned URL auth:** `/files/?sig=` paths are now correctly exempt from Caddy's
  Bearer check — presigned downloads no longer fail with 401.
- **Logs:** raw `kirocrew token` output is no longer logged when a token can't be parsed.

---

## Known Limitations

- **Captain autopilot on Claude/Codex backends is not supported.** Drive non-kiro
  crews manually with `dispatch`, `pickup`, and `steer`.
- **Claude OAuth tokens expire after ~8 hours.** The first crew to hit expiry refreshes
  inside its container; other running crews may fail. Workaround: re-login or use
  `GA_CREW_ANTHROPIC_API_KEY`.
- **Default install is unauthenticated.** `GA_API_KEY` is empty by default. Set it on
  any machine reachable from another host.

---

## Upgrading

1. Update `ghostship.conf`:
   - Replace `GA_INCLUDE_CLAUDE_AGENT=true` → `GA_AGENT_BACKENDS=claude`
   - Replace `GA_INCLUDE_CODEX_AGENT=true` → `GA_AGENT_BACKENDS=codex`
   - Remove any reference to `GA_INCLUDE_CLAUDE_AGENT` or `GA_INCLUDE_CODEX_AGENT`
     entirely (even `=false` triggers the error).
2. Re-run `./install.sh`. The crew image will be rebuilt to pick up the new base image
   and any newly enabled backends.
3. Existing crews use the old image until nuked and re-launched. Evacuate anything you
   need first with `evac`.
