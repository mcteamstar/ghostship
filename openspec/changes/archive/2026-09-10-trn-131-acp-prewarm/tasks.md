## 1. Configuration

- [x] 1.1 Add `GA_PREWARM_ENABLED` (bool, default `false`) and `GA_PREWARM_TTL_SECS` (int) to `transport/config.py` `Config.from_env()`, with the same env-var pattern as existing `GA_*` settings
- [x] 1.2 Cap the effective warm-lifetime hint at the crew's effective `session.timeout_secs` (currently 300) so a warm marker can never outlive the idle reaper
- [x] 1.3 Document `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` (defaults + effect) in `docs/configuration.md`

## 2. Transport prewarm mechanism

- [x] 2.1 Add a per-crew warm-marker map (`{crew_id: warmed_at}`) plus a guarding lock in `transport/lifecycle.py`, mirroring the `_startup_events_lock` / `_task_timestamps_lock` patterns
- [x] 2.2 Implement `_prewarm_crew(crew, crew_id)` that returns early with a `disabled` status when `GA_PREWARM_ENABLED` is false
- [x] 2.3 In `_prewarm_crew`, when the warm marker is fresh (within the capped TTL) and the container is running, return `already_warm` without a second warm-up request
- [x] 2.4 In `_prewarm_crew`, call `_ensure_crew_running` to enforce the memory (`GA_MIN_FREE_MEM_GB`) and active-crew (`GA_MAX_ACTIVE_CREWS`) gates, per-crew start serialisation, and gateway readiness; translate a gate `RuntimeError` into a `blocked:<gate>` status naming the gate
- [x] 2.5 Implement the session warm-up step (D1): issue the gateway session/readiness request that forks the `kiro-cli-chat` session and completes the ACP handshake without dispatching a real task; route it through `_crew_api_with_recovery` so the Phase-0 503 "still spawning" tolerance applies
- [x] 2.6 On successful warm-up, update the warm marker and return `warmed`; on a warm-up request failure return `error:<msg>` and leave dispatch behaviour unchanged
- [x] 2.7 Add `_require_crew`-based handling so an unknown `crew_id` returns an error and performs no start or fork

## 3. Surface: MCP tool + REST endpoint

- [x] 3.1 Add a `prewarm` MCP tool in `transport/server.py` that validates `crew_id` and delegates to `_prewarm_crew`, returning `{crew_id, status}`
- [x] 3.2 Add a `POST /crews/{crew_id}/prewarm` route in `transport/server.py`, mirroring the `POST /crews/{crew_id}/dashboard` handler for `GA_API_KEY` auth and response shape
- [x] 3.3 Ensure both surfaces return the full status set: `warmed` | `already_warm` | `disabled` | `blocked:<gate>` | `error:<msg>`

## 4. Tests

- [x] 4.1 Unit test: `_prewarm_crew` returns `disabled` and performs no start/fork when `GA_PREWARM_ENABLED` is false
- [x] 4.2 Unit test: prewarm on a stopped crew (gates permitting) starts the container, waits for the gateway, issues exactly one warm-up request, and returns `warmed`
- [x] 4.3 Unit test: prewarm on an already-warm crew (fresh marker, running container) returns `already_warm` with no restart and no second warm-up request
- [x] 4.4 Unit test: prewarm is non-destructive — no `/api/spawn` real-task dispatch, no mail, no spec/workspace write is issued by the operation
- [x] 4.5 Unit test: memory gate and active-crew gate each produce the corresponding `blocked:<gate>` status and no container start
- [x] 4.6 Unit test: warm marker TTL is capped at `session.timeout_secs` even when `GA_PREWARM_TTL_SECS` is larger
- [x] 4.7 Unit test: unknown `crew_id` returns an error and takes no action
- [x] 4.8 REST test: `POST /crews/{crew_id}/prewarm` succeeds with valid `GA_API_KEY` and is rejected without it, matching the dashboard-endpoint auth behaviour

## 5. Validation

- [x] 5.1 Run `openspec validate trn-131-acp-prewarm --strict --store repo` and resolve any findings
- [x] 5.2 Run the transport test suite and confirm no regression in the dispatch, pickup, or idle-stop paths when prewarm is disabled
