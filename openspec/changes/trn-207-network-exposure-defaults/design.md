# Design: TRN-207 Network Exposure Defaults

See `proposal.md` for motivation and scope.

## Context

The install produces two public-facing components:

```
Host network
  └─ 0.0.0.0:<PORT>   (published by ga-portal/Caddy)
  └─ 0.0.0.0:<DASH_RANGE>  (published by ga-portal/Caddy)

ga-portside (internal Podman network)
  ├─ ga-portal (Caddy)  — listens on :<PORT>, admin on 0.0.0.0:2019
  └─ ga-transport       — listens on HOST:PORT (default 0.0.0.0:64057)

ga-starboard (internal Podman network)
  └─ ga-transport + crew containers
```

Key facts that shape decisions:

- **Port 2019 is not published** as a host port in `compose.yml`. It is bound
  to `0.0.0.0` *inside* the ga-portal container, so it is only reachable from
  other containers on `ga-portside`. The proposal's "0.0.0.0:2019" finding
  refers to the in-container bind, not the host.
- **ga-transport `HOST`** defaults to `0.0.0.0` inside the container; Caddy is
  the only container on `ga-portside` that talks to it, so this has no
  host-network exposure today. However, if port 64057 were ever accidentally
  published on the transport container, `HOST=0.0.0.0` would expose it without
  auth.
- **`GA_API_KEY` empty** is the real open-door: without a key, Caddy's
  `forward_auth` stanza is skipped and every MCP call succeeds.
- **WebSocket route** was intentionally placed before the catch-all in TRN-189
  to avoid a Caddy limitation. The comment says "no auth regression: reaching
  this port at all required the gs_session." That reasoning is valid for HTTP
  sessions but incomplete — a direct WebSocket connection skips session
  validation at the Caddy layer entirely.
- **`X-Forwarded-For` rate-limit key** — Caddy appends to XFF by default.
  The first hop the middleware reads is the real client only when Caddy is the
  first trusted proxy. If Caddy is configured to *append*, the first XFF hop
  is still client-controlled before Caddy adds its own entry at the end.
- **Dashboard login throttle** — already fixed in `dashboard.py` (uses
  `request.client.host`, not XFF). The proposal finding predates the fix; code
  and spec already match `dashboard-session-auth/spec.md`.

## Goals / Non-Goals

**Goals:**

- Enforce that a non-loopback bind requires `GA_API_KEY` to be set, or print a
  prominent warning that the install is unauthenticated.
- Add `GA_REQUIRE_API_KEY` as an explicit override so operators who knowingly
  want unauthenticated local access can silence the warning.
- Fix the WebSocket route: add session validation *within the transport* for
  WebSocket upgrade paths so the auth gate is enforced regardless of Caddy
  route ordering.
- Tighten the Caddy admin API to reject requests from origins other than the
  transport container (`ga-transport`) by enabling Caddy's built-in `origins`
  enforcement.
- Fix the `X-Forwarded-For` source-IP extraction in `RateLimitMiddleware` to
  use the *last* XFF hop (the one Caddy appended) rather than the *first*
  (client-controlled). Alternatively: use the ASGI client address directly,
  since the transport only receives requests from Caddy on `ga-portside` and
  the ASGI client address is always the Caddy container IP. Decision: **use
  ASGI client address** when all traffic flows through Caddy, but expose a
  `GA_TRUSTED_PROXY` env var so operators who front with an external proxy can
  opt into XFF trust.
- Update the one test (`test_rate_limiting.py`) that asserts first-hop XFF
  behaviour.

**Non-Goals:**

- TLS enablement by default — already controlled by `GA_PORTAL_TLS_MODE`; this
  change adds a docs note only.
- Changing the Caddy admin port or moving it to localhost — would break
  `_caddy_admin_url()` without any security benefit (port 2019 is not
  host-published).
- Crew-level authentication — out of scope.

## Decisions

### D1 — Bind-address gate: warning + env-var override, not hard block

**Options considered:**
- A. Block non-loopback bind unless `GA_API_KEY` is set. → Breaking for
  shared-network installs that intentionally run without auth.
- B. Print a startup warning on non-loopback + no key; add
  `GA_REQUIRE_API_KEY=warn|error|off` to control severity. → Chosen.
- C. Default bind address to 127.0.0.1 in the compose template. → Silently
  breaks any install expecting external access without a key; too surprising.

**Decision:** Option B. `install.sh` emits a prominent `WARNING` when
`GA_API_KEY` is empty and the published port binds to anything other than
`127.0.0.1`. `GA_REQUIRE_API_KEY=error` turns the warning into an exit.
`GA_REQUIRE_API_KEY=off` silences it. Default is `warn`.

### D2 — WebSocket auth bypass: transport-side session check

The Caddy `forward_auth` gate cannot cover WebSocket upgrades (see TRN-189
comment). The fix must be in the transport, not in Caddy config.

**Options considered:**
- A. Add a transport-side guard in `BearerAuthMiddleware` that rejects
  WebSocket scopes whose origin is not on an allowlist. → Too blunt; breaks
  legitimate non-browser WS clients.
- B. For WebSocket scopes arriving on a dashboard port, verify that the ASGI
  handshake carries a valid `gs_session` cookie before upgrading. → Chosen.
  Keeps auth in `dashboard.py` where session state lives.
- C. Add Caddy `forward_auth` to the WS route using a custom Caddy module. →
  Requires a custom Caddy build; not feasible.

**Decision:** Option B. The transport's WebSocket proxy path for crew dashboard
ports SHALL check `gs_session` validity via `SessionStore.validate()` before
completing the upgrade. Unauthenticated WS upgrade attempts receive HTTP 401.

### D3 — Rate-limit source IP: ASGI client address + trusted-proxy opt-in

See Goals section. Default: use `scope["client"][0]` (ASGI peer address).
When `GA_TRUSTED_PROXY=1` (or an IP), trust the **last** XFF hop instead.
This matches how reverse-proxy deployments are supposed to work: Caddy appends
to XFF, so the last entry is Caddy's view of the client.

The existing spec (`rate-limiting`) says "first hop of X-Forwarded-For."
That spec requirement is wrong for the Caddy-in-front topology and must be
updated to reflect the new behaviour.

### D4 — Caddy admin origins enforcement

Caddy 2.6+ supports `"admin": {"origins": ["..."]}` to restrict which
HTTP `Origin` headers the admin API accepts. Setting this to the
`ga-transport` container's DNS name (`http://ga-transport`) blocks any other
container or process on `ga-portside` from using the admin API.

This does not change the bind address. Port 2019 stays on `0.0.0.0` inside
the container (required for Caddy's own internal routing).

### D5 — TLS cleartext: documentation only

The findings note `GA_PORTAL_TLS_MODE=off` as default. Changing the default
would be a breaking install change for the common local-only case. This change
adds a note to `docs/configuration.md` about the security implication and
links to the TLS setup section.

## Risks / Trade-offs

**[Risk] D1 warning ignored.** The warning is emitted by `install.sh` but not
re-checked at runtime. An operator who redirects stdout/stderr may miss it.
→ Mitigation: also log at startup from the transport process itself
(`WARNING` level) when `GA_API_KEY` is absent and `HOST` is not a loopback
address.

**[Risk] D2 WS session check adds latency.** `SessionStore.validate()` is an
in-memory lookup — negligible overhead.

**[Risk] D3 ASGI-client key collapses all Caddy-proxied traffic into one
bucket.** Every request through Caddy appears to come from the Caddy container
IP, so all callers share one rate-limit bucket per endpoint.
→ Mitigation: when `GA_TRUSTED_PROXY=1`, the last-hop XFF IP is used, giving
per-client granularity. The default (no trusted proxy) is conservative and
safe; operators on shared networks should set `GA_TRUSTED_PROXY`.

**[Risk] D3 spec update changes behaviour for existing deployments.**
Any deployment that relied on the first-hop XFF bucket will see a different
key. No breakage expected since this is a security fix, not a functional
change.

**[Risk] D4 origins enforcement may need adjustment per Caddy version.**
The `origins` field was stabilised in Caddy 2.6. The compose.yml pins
`docker.io/caddy:2` (floating major). → Mitigation: pin to `caddy:2.8` or
later in the compose template. (Tracked in TRN-213 for pinning; note the
dependency here.)

## Migration Plan

All changes are backward-compatible for the default install:

1. `install.sh` warning (D1) — new output on non-loopback + no key; operators
   who pipe output to logs will see it. No action required unless they want to
   silence it.
2. Caddy config change (D4) — regenerated at `install.sh` time; no manual
   migration.
3. Rate-limit key change (D3) — in-memory state resets on restart anyway; no
   migration needed.
4. `GA_TRUSTED_PROXY` — new env var; absent = old safe default (ASGI client).
   Existing installs are unaffected.

Breaking case: operators who set `GA_REQUIRE_API_KEY=error` and run without a
key will get a hard failure. This is intentional and opt-in.

## Open Questions

- Should the bind-address warning be surfaced in the Ghostship dashboard UI as
  well, or is the install-time warning sufficient? (Deferrable — UI changes are
  out of scope for this change; can be a follow-on.)
