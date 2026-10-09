# Proposal

Source: independent review of `release/0.6.0` at `ee0b3b8` (2026-10-09), run on the Claude backend. Reviewers: **S** security, **Q** quality, **T** test coverage, **D** docs. "Reproduced" means the reviewer or a live check ran code to confirm it; everything else is from reading the code and needs confirming during assessment. Target: a release after 0.6.0.

Full reviewer reports: crew `ghostship-indy-060` tasks `169e9101b28e91e4` (security), `d615d73e3b7c9e37` (quality), `408dea89af5f6789` (test coverage), `45df3b672a262c4c` (docs) — retrieve with `pickup(task_id, crew_id)` while the crew exists. Line numbers refer to `ee0b3b8` and may drift. Next step for whoever picks this up: work through **Assess first**, then write specs, design and tasks with `openspec instructions <artifact> --change <name>`.

## Why

A default install exposes the MCP control surface without authentication on all interfaces, and several auth edges trust client-controlled input. The docs and changelog now say so plainly, but the default is unchanged.

## Findings

| Severity | Finding | Where | Who | Status |
|---|---|---|---|---|
| High | Default install: `GA_API_KEY` empty and `ga-portal` published on `0.0.0.0:${PORT}`, so anyone who can reach the host can use every MCP tool. Docs say `127.0.0.1`. | `install.sh:59`, `:794`; `auth.py:457-508`; `configuration.md:9`, `:176` | S, D | Read only (not exploited live) |
| High | Rate limiter keys on the first `X-Forwarded-For` hop, which the client controls if Caddy appends. A test locks in the current behaviour. | `auth.py:244-253`; `test_rate_limiting.py:223` | S, Q, T | Depends on Caddy append behaviour — unverified |
| High | Dashboard `forward_auth` bypass: the per-crew Caddy server's WebSocket route matches `Connection: Upgrade` first and skips the session check. | `caddy.py:187-213`; `server.py:1105` | S | Read only — reproduce on a disposable instance |
| Medium | Caddy admin API on `0.0.0.0:2019`; a route added through it can read `/run/secrets/*` placeholders. The transport itself uses it at `http://ga-portal:2019` to register crew dashboards (`caddy.py:309-311`), so it cannot simply move to localhost. | `install.sh:900` | S | Read only |
| Medium | Cleartext by default (`GA_PORTAL_TLS_MODE=off`): bearer key, session cookie (no `Secure`) and presigned URLs in plaintext. | `install.sh:101`; `dashboard.py:154` | S | Read only |
| Low | Dashboard login throttle keyed on Caddy's IP, so one client can lock everyone out. | `dashboard.py:136` | S | Read only |

## Assess first

- Reproduce the default exposure, the `X-Forwarded-For` bypass and the `forward_auth` bypass on a disposable host before triage.
- Decide the default posture: loopback bind, required API key, or an explicit insecure flag.

## What Changes

- Default to loopback, or refuse a non-loopback bind without `GA_API_KEY`.
- Key rate limits on the socket peer unless it is a trusted proxy; update the test that asserts the current behaviour.
- Put `forward_auth` on the WebSocket route (match `Upgrade: websocket`), and have the transport check the session itself.
- Restrict the Caddy admin API to the transport: keep it on the internal `ga-portside` network only and/or enable Caddy's admin `origins` enforcement. Binding it to localhost would break dashboard registration.
- Fix the login throttle key.

## Capabilities

### New Capabilities

- None expected.

### Modified Capabilities

- `rate-limiting`, `transport/caddy-proxy`, `transport/dashboard-auth`, `transport/dashboard-login`, `transport/tls`, `installation`.

## Impact

`scripts/install.sh` (compose and Caddy config), `transport/auth.py`, `transport/caddy.py`, `transport/dashboard.py` (throttle). Possibly breaking for anyone relying on remote access without a key.
