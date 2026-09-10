## Why

Spec-ops crews run with `session.eager_spawn = false` (TRN-117 headless overrides), so the `kiro-cli-chat` session process — and the ACP (Agent Context Protocol) connection between the gateway and that session — is not established until the first `dispatch` arrives. The first task on a freshly-launched or idle-recovered crew therefore pays the full cold-start cost: session fork (~340 MB pre-fork was the reason eager_spawn was disabled), ACP handshake, and MCP server wiring, all on the critical path before any real work begins. For an SDD pipeline where Raven dispatches Ghost, then Banshee, then Reaper in sequence, this cold-start tax is paid repeatedly and is visible as multi-second stalls at the start of each persona hand-off.

We want the memory savings of `eager_spawn = false` at idle **and** a warm ACP connection ready the moment a dispatch is likely — so cold-start latency is hidden behind a controlled pre-warm rather than charged to the user-visible task.

## What Changes

- Add a **prewarm mechanism** to the transport that establishes the crew's ACP session connection ahead of an expected dispatch, so the session process is already forked and the ACP handshake already complete when the real task arrives.
- Add a transport-side `prewarm` operation (MCP tool + `POST /crews/{crew_id}/prewarm` REST endpoint) that triggers a pre-warm for a named crew on demand, returning promptly without blocking on a real task.
- Pre-warm SHALL be **idempotent and non-destructive**: pre-warming an already-warm crew is a cheap no-op; pre-warming never dispatches real work, mutates specs, or sends mail.
- Pre-warm SHALL respect the existing memory and active-crew gates (`GA_MIN_FREE_MEM_GB`, `GA_MAX_ACTIVE_CREWS`) — it starts a container / forks a session only when the same guards that gate `_ensure_crew_running` and dispatch would allow it.
- A warmed session SHALL still be reaped by the existing `session.timeout_secs` idle timer if no dispatch follows, so pre-warming cannot pin memory indefinitely.
- Add operator configuration to bound pre-warm behaviour: an enable flag and a warm-lifetime hint, driven by environment variables with headless-safe defaults.

## Capabilities

### New Capabilities
- `acp-prewarm`: A transport mechanism and operation to pre-establish a crew's ACP session connection ahead of an expected dispatch, hiding cold-start latency while preserving the idle-memory savings of deferred session spawn. Covers the trigger surface (MCP tool + REST endpoint), idempotency, the interaction with memory/active-crew gates, and reap-after-idle behaviour.

### Modified Capabilities
<!-- No existing capability's requirements change. crew-lifecycle's eager_spawn=false
     override is unchanged; prewarm is an additive, on-demand warm-up layer on top of
     the existing deferred-spawn behaviour, not a modification of it. -->

## Impact

- **Code**: `transport/lifecycle.py` (new prewarm helper alongside `_ensure_crew_running`; reuse of the gateway readiness / cookie machinery), `transport/server.py` (new MCP tool + `POST /crews/{crew_id}/prewarm` route), `transport/config.py` (new env-var-backed settings), `transport/monitors.py` (optional: opportunistic pre-warm hook — deferred to design).
- **Config / env**: new `GA_PREWARM_ENABLED` (default off) and `GA_PREWARM_TTL_SECS` (warm-lifetime hint); documented in `docs/configuration.md`.
- **Behaviour**: no change to idle memory footprint when prewarm is not triggered; when triggered, one crew's session process is forked early and counts toward the active-crew / memory gates exactly as a dispatch would.
- **Dependencies**: none new — reuses the existing Podman client, gateway readiness probe, and KiroCrew's own `/api/spawn` / session surface.
- **Compatibility**: additive and opt-in; existing dispatch, pickup, and idle-stop paths are unchanged when prewarm is disabled.
