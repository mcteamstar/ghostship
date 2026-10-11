# TRN-220 — Unix-Socket Peer-Cred Validation on the Internal Gateway API

- **Plane ticket:** TRN-220
- **Context:** KiroCrew 0.9.0 upgrade (`0.9.0-insider.4`), from `0.8.0` baseline
- **Upstream change:** PR #2424 / issue #302 — "Verify internal-API session claims via unix-socket peer creds"
- **Priority verdict (from research report):** **Conditional — safe today, needs verification.** Not a hard break under the current architecture; a latent break if ghostship's call pattern ever changes.

## What changes

KiroCrew 0.9.0 adds **peer-credential validation** to the gateway's **internal
API** — the request path authenticated with `X-Internal-Secret` (and
`X-Session-Key`). On that path, the gateway now reads the connecting peer's OS
credentials off the unix socket and rejects a caller whose UID does not match
the gateway process owner (`kirocrew`), even if the shared secret is correct.
Possession of `.local_secret` is no longer sufficient on its own.

This proposal records the assessment of ghostship's exposure, pins the
invariant that keeps ghostship safe, and adds a guardrail so a future change
cannot silently route an internal-API call across a UID boundary.

## Why

The transport talks to each crew gateway over REST. There are two distinct
auth paths, and 0.9.0 only tightens one of them:

1. **Dashboard cookie path** (external) — `Cookie: mc_token_5476=<value>` +
   `Origin`. This is what ghostship actually uses everywhere. Peer-cred
   validation does **not** apply here.
2. **Internal-secret path** — `X-Internal-Secret` + `X-Session-Key`. This is
   the path 0.9.0 now peer-cred-gates.

In ghostship today:

- `transport/lifecycle.py::_crew_api()` sends **only** `Cookie` + `Origin`
  (the external path). It never sends `X-Internal-Secret`.
- The container scripts in `transport/container_scripts/` do **not** call the
  REST API at all — they run inside the container via
  `podman.container_exec()` as the `kirocrew` user and read/write SQLite and
  files directly.
- Raven, dispatched inside the container, is explicitly told to use the
  **cookie** path and warned off the internal-secret headers
  (`transport/captain.py::_RAVEN_GATEWAY_ORIENTATION`).

So ghostship is safe *today*: it either avoids the internal path entirely, or
only touches it from a process already running as `kirocrew` (same UID as the
gateway, so the peer-cred check passes). The risk is purely latent — if a
later change calls the internal API from the **transport host process**
(a different UID), the new check will reject it. This proposal makes that
invariant explicit and testable rather than tribal knowledge.

## Affected ghostship files / functions

| File | Symbol | Relevance |
|---|---|---|
| `transport/lifecycle.py` | `_crew_api()` (≈L346) | Sole REST entry point; uses cookie path, must never add `X-Internal-Secret`. |
| `transport/lifecycle.py` | `_mint_internal_cookie()` (≈L1336) | Mints a 127.0.0.1-bound cookie exchanged *inside* the container — the loopback cookie, not the internal secret, is what crew-member REST calls rely on. |
| `transport/lifecycle.py` | `_write_dashboard_cookie()` (≈L312) | Writes `.dashboard_cookie` (cookie path) for Raven. |
| `transport/captain.py` | `_RAVEN_GATEWAY_ORIENTATION` (≈L53) | Documents cookie path; explicitly forbids `X-Internal-Secret` / `X-Session-Key`. |
| `transport/server.py` | captain-dispatch cookie refresh (≈L3164) | Reads `internal_cookie` from registry, writes it to `.dashboard_cookie`. |
| `transport/container_scripts/*.py` | all | Run as `kirocrew` via `container_exec`; no REST calls — peer-cred check never applies. |

## Scope

This is a **guardrail + verification** change, not a behaviour change to a
working feature. It adds:

1. A documented invariant: ghostship authenticates to the crew gateway with
   the dashboard cookie only; `X-Internal-Secret` is never sent from the
   transport host.
2. A regression test asserting `_crew_api` emits no internal-secret header.
3. A verification step against `0.9.0-insider.4` confirming the cookie path is
   unaffected by the peer-cred change.

No functional code path changes under the current architecture.
