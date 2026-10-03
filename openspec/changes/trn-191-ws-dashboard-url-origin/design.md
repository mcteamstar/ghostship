## Context

TRN-189 fixed the Caddy `forward_auth` path so WebSocket upgrade requests now
reach the KiroCrew gateway instead of being dropped at the proxy. The upgrades
are now rejected one layer deeper, by the gateway itself, with
`403 WebSocket origin not allowed`. HTTP requests over the identical
cookie-injection path return 200 — the failure is WS-specific.

See `proposal.md` for the full root-cause trace. In short: the gateway's
`check_origin(request, require=True)` validates the handshake `Origin` against
`app["allowed_origins"]`, a set built once at startup from `dashboard.url` in
the crew config. Ghostship never sets `dashboard.url`, so it stays at the
KiroCrew default (empty string) and `build_allowed_origins` falls back to
loopback-only. The transport's WS proxy sends
`Origin: http://gs-{crew_id}:5476` (the internal container hostname), which is
neither loopback nor in the set.

Constraints shaping the approach:
- KiroCrew deep-merges `config.local.json` over `config.json` on every start,
  so a value written into the patch takes effect with no restart-logic change.
- `allowed_origins` is computed at gateway startup, not per-request, so the
  config must carry the right value before the gateway process boots.
- The container hostname and gateway port are already known to the transport
  as module-level constants (`CREW_CONTAINER_PREFIX`, `CREW_GATEWAY_PORT` in
  `server.py`).

## Goals / Non-Goals

**Goals:**
- Make the gateway's `allowed_origins` include its own container origin so the
  transport's proxied WS `Origin` is accepted (101, not 403).
- Keep the fix purely config-side — no gateway code change, no new restart or
  reload path.
- Preserve the existing security posture: no external origin becomes allowed.

**Non-Goals:**
- Changing how the transport injects the `Origin` header (TRN-189 already set
  it correctly; this change makes the gateway accept it).
- Altering `build_allowed_origins` or `check_origin` in KiroCrew itself.
- Supporting a per-crew custom public dashboard URL — out of scope; the value
  set here is the internal gateway origin only.

## Decisions

### Decision: Set `dashboard.url` in `_patch_crew_config` rather than patching the gateway

Add `dashboard.url = http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}`
to the dict `_patch_crew_config` writes into `config.local.json`.

- **Why:** The gateway already derives `allowed_origins` from `dashboard.url`;
  supplying the value it was always meant to have is the minimal, in-contract
  fix. It needs no change to KiroCrew's own code and rides the existing
  deep-merge on start.
- **Alternative — hard-code the container origin into KiroCrew's
  `build_allowed_origins` fallback:** rejected. It would require forking or
  patching KiroCrew, couples the gateway to the Ghostship naming scheme, and
  breaks the TRN-188 backward-compatibility finding that the integration
  surface needs no changes.
- **Alternative — relax `check_origin` to skip validation for WS:** rejected.
  That removes a real CSRF/websocket-hijacking defence for every crew; the
  origin check should stay on, with the legitimate origin allow-listed.

### Decision: Compose the value from the existing constants, do not re-derive the hostname

Reuse `CREW_CONTAINER_PREFIX` and `CREW_GATEWAY_PORT`. If `lifecycle.py` does
not already import them from `server.py`, import them (or pass the composed
value in) rather than re-declaring literals.

- **Why:** A second copy of the `gs-` prefix or the `5476` port drifts from the
  canonical definition the rest of the transport uses to name and dial the
  container. The `Origin` the proxy sends and the origin the config allows must
  be byte-identical or the 403 returns.

### Decision: Rely on local-over-base merge precedence; do not guard against a pre-existing value

`config.local.json` overrides `config.json`, so unconditionally setting
`dashboard.url` in the local patch is correct — Ghostship owns this file and
no earlier layer sets a conflicting value.

- **Why:** Task 1.3 verifies the merge direction; once confirmed
  (local overrides base), a conditional "only if unset" check adds complexity
  with no benefit, because the base never sets it.

## Risks / Trade-offs

- **[Origin string mismatch]** → If the composed `dashboard.url` differs from
  the `Origin` the proxy injects by even a port or scheme, the 403 persists.
  Mitigation: both sides are built from the same two constants; the unit test
  (3.1) asserts the patched value equals `http://gs-{crew_id}:5476`, and the
  end-to-end validation (4.3) confirms 101 in browser devtools.
- **[KiroCrew changes the config key or the derivation]** → A future KiroCrew
  version could rename `dashboard.url` or change how `allowed_origins` is
  built. Mitigation: TRN-188 confirmed the 0.8.0 upgrade keeps this surface
  backward-compatible; the e2e step would catch a regression on any later bump.
- **[Scope creep of allowed origins]** → Mis-setting the value to a wildcard or
  external host would weaken origin checking. Mitigation: the value is a fixed
  internal container origin reachable only from `ga-net`; the spec requires the
  external-exclusion property and the test pins the exact string.

## Migration Plan

1. Land the `_patch_crew_config` change plus the unit test on the transport.
2. Deploy the updated transport to academy.
3. Launch a fresh crew with `dashboard=True` — existing already-running crews
   keep their current (empty) `dashboard.url` until relaunched, which is
   acceptable because the fix targets new launches; no data migration is
   needed.
4. Validate 101 in browser devtools and confirm sessions list / live updates /
   import modal work.

**Rollback:** revert the one-line patch and redeploy the transport. No
persisted state changes, so rollback is clean; crews launched under the fix
simply carry an extra (harmless, correct) `dashboard.url` in their local
config.
