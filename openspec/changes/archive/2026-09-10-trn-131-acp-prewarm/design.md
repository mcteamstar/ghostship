## Context

See `proposal.md` (Why) for motivation. The relevant current state:

- Spec-ops crews are launched with headless config overrides (TRN-117), including `session.eager_spawn = false` and `session.timeout_secs = 300`. The `kiro-cli-chat` session process is therefore not forked at gateway start; it is forked on the first `dispatch`, at which point the gateway also completes the ACP handshake with that session and wires MCP servers. This fork + handshake is the cold-start cost.
- `transport/lifecycle.py` already owns the crew start machinery: `_ensure_crew_running` (per-crew-serialised probe-then-start, with the memory gate `GA_MIN_FREE_MEM_GB` and active-crew gate `GA_MAX_ACTIVE_CREWS`), `_wait_gateway` (polls `/api/ready`), `_mint_cookie`, and `_crew_api_with_recovery` (three-phase recovery, including Phase 0's short bounded 503 retry that already tolerates "task still spawning").
- Dispatch flows through `_crew_api_with_recovery(..., "POST", "/api/spawn", ...)`; the gateway's `/api/spawn` surface is what triggers the session fork on a cold crew.
- REST crew endpoints already exist (e.g. `POST /crews/{crew_id}/dashboard`) and are `GA_API_KEY`-gated, giving a template for the new prewarm route.

## Goals / Non-Goals

**Goals:**
- Provide an on-demand, idempotent warm-up that forks the session and completes the ACP handshake before a real dispatch, reusing the existing start/gate/readiness machinery rather than duplicating it.
- Keep idle memory unchanged when prewarm is not triggered, and keep a warmed-but-unused session reclaimable by the existing idle timer.
- Make prewarm opt-in and operator-bounded.

**Non-Goals:**
- Re-enabling `session.eager_spawn` — this design deliberately keeps the deferred-spawn default and layers an opt-in warm-up on top; it does not modify the `crew-lifecycle` headless-override requirements.
- Automatic/predictive pre-warming across an SDD hand-off chain (Raven → Ghost → Banshee → Reaper). An opportunistic monitor hook is noted under Open Questions but is out of scope for this change.
- Keeping a session warm past `session.timeout_secs` — prewarm never extends the idle timer.

## Decisions

**D1 — Warm the session by driving the gateway's own session surface, not a new gateway API.**
The cheapest reliable way to fork the session and complete the ACP handshake is to make the gateway do exactly what a dispatch's first `/api/spawn` does, minus real work. The transport SHALL trigger the session fork through the gateway's existing readiness/session surface (a warm-up request that establishes the session/ACP connection without enqueuing an agent task). Rationale: the ACP handshake is internal to the gateway↔session boundary; the transport cannot perform it directly, so it must cause the gateway to perform it. Reusing the existing surface avoids adding a KiroCrew-side endpoint and keeps the transport as the only component that changes.
_Alternative considered:_ dispatch a trivial no-op task (e.g. "reply OK") and immediately discard it. Rejected: it consumes a real turn/model call, pollutes the task list and timestamps, risks mail/spec side effects, and violates the non-destructive requirement.

**D2 — Reuse `_ensure_crew_running` for the container/gate/readiness path; add a thin `_prewarm_crew` on top.**
`_prewarm_crew(crew, crew_id)` SHALL call `_ensure_crew_running` (which already enforces the memory and active-crew gates, serialises concurrent starts per crew, and waits for the gateway), then issue the session warm-up (D1) and record a warm marker. Rationale: the gates and per-crew start lock are exactly the semantics prewarm needs; re-implementing them would drift. The active-crew gate is naturally skipped for an already-running crew because `_ensure_crew_running` returns early on a healthy running container.
_Alternative considered:_ a standalone start path for prewarm. Rejected: duplicates gate logic and the startup-serialisation Event.

**D3 — Idempotency via a per-crew warm marker checked before the warm-up request.**
Track warm state per crew (in-memory `{crew_id: warmed_at}`, guarded by a lock like the existing `_startup_events_lock` / `_task_timestamps_lock` patterns). If a crew is already running and `warmed_at` is within the effective warm-lifetime, `prewarm` returns `already_warm` without a second warm-up request. The marker is advisory: a missed marker at worst causes one extra idempotent warm-up request, never real work. Rationale: cheap, transport-local, and consistent with the existing in-memory bookkeeping. The gateway's own session state is the source of truth; the marker only suppresses redundant requests.

**D4 — Configuration: `GA_PREWARM_ENABLED` (default off) and `GA_PREWARM_TTL_SECS`, read via `Config.from_env()`.**
`GA_PREWARM_ENABLED` defaults to disabled so no behaviour changes on existing installs. `GA_PREWARM_TTL_SECS` is the warm-lifetime hint used for D3's freshness check and is capped at the effective `session.timeout_secs` (currently 300) so the marker can never claim a session is warm after the idle timer would have reaped it. Rationale: mirrors the existing `GA_*` env-var + `docs/configuration.md` convention and keeps the memory-footprint promise honest.

**D5 — Surface parity: MCP tool `prewarm` + `POST /crews/{crew_id}/prewarm`, both thin wrappers over `_prewarm_crew`.**
The REST route mirrors the existing `POST /crews/{crew_id}/dashboard` handler for auth and shape. Both return `{crew_id, status}` where status ∈ `{warmed, already_warm, disabled, blocked:<gate>, error:<msg>}`. Rationale: consistent operator surface; the REST route lets an external orchestrator (e.g. a Raven-side pre-dispatch hook) warm the next persona's crew.

## Risks / Trade-offs

- **Warm-up request forks memory earlier than a real dispatch would** → Mitigation: gated by `GA_MIN_FREE_MEM_GB` / `GA_MAX_ACTIVE_CREWS` exactly like a dispatch, and reaped by `session.timeout_secs` if unused; disabled by default.
- **Warm marker goes stale vs. the gateway's real session state** (session reaped between marker write and next prewarm) → Mitigation: marker is advisory and TTL-capped at `session.timeout_secs`; a stale marker only ever triggers one extra idempotent warm-up, never real work or a double fork (the gateway session surface is itself idempotent for an already-live session).
- **Warm-up request races a concurrent real dispatch on the same crew** → Mitigation: `_ensure_crew_running`'s per-crew start Event already serialises the start; the warm-up request and a dispatch both go through the gateway's session surface, which tolerates an already-forked session (Phase-0-style 503 tolerance already exists in `_crew_api_with_recovery`).
- **Prewarm depends on the exact gateway surface used to fork the session (D1)** → Mitigation: pin the chosen surface behind `_prewarm_crew` so a future KiroCrew change is a one-function fix; if the surface is unavailable, prewarm returns `error:` and dispatch behaviour is unchanged (prewarm is purely additive).

## Migration Plan

Additive and opt-in. Deploy with `GA_PREWARM_ENABLED` unset (default) → zero behaviour change; existing dispatch/pickup/idle-stop paths are untouched and no new memory is held. Enable per-deployment by setting `GA_PREWARM_ENABLED=true`. Rollback = unset the flag (or roll back the transport image); no persisted state or registry schema change is introduced, so rollback is immediate and safe.

## Open Questions

- Should `transport/monitors.py` gain an opportunistic pre-warm hook that warms the next persona's crew during an SDD hand-off (e.g. when Raven's pickup observes a "spectre done" mail)? Deferred: it does not change these specs or the `_prewarm_crew` design — it would be a later caller of the same operation — so it is safe to answer after this change lands.
