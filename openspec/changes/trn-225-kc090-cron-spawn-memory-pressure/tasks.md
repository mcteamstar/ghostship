# Tasks — TRN-225 Cron spawn refused under memory pressure

## Config

- [x] Add `ga_spawn_pressure_escalate_cycles: int = 3` to `TransportConfig` in `transport/config.py` (after line 229)
- [x] Add `ga_spawn_pressure_escalate_cycles=_env_int("GA_SPAWN_PRESSURE_ESCALATE_CYCLES", "3")` to the loader in `transport/config.py` (after line 377)
- [x] Add `GA_SPAWN_PRESSURE_ESCALATE_CYCLES = cfg.ga_spawn_pressure_escalate_cycles` to the config mirror block in `transport/server.py` (alongside lines 428–431)

## Transport — probe & classification

- [x] Add `_MEMORY_PRESSURE_MARKER` constant and `_MemoryPressureSkip(RuntimeError)` subclass to `transport/server.py`
- [x] Add `_check_in_memory_pressure()` helper using `_get_host_memory_gb_cached()` and `GA_RESOURCE_CRITICAL_GB` (fail-open on `None`/exception)
- [x] Add `_is_memory_pressure_refusal(resp)` helper classifying 429/503 bodies that name memory pressure
- [x] In `_dispatch_captain_checkin()` (server.py ~line 3131), probe memory before the `/api/spawn` call (~line 3212) and raise `_MemoryPressureSkip` when below critical
- [x] Wrap the `_crew_api_with_recovery` spawn call to re-raise a gateway memory-pressure refusal as `_MemoryPressureSkip` (do NOT route it through recovery retry)

## Transport — counter & escalation

- [x] Add `consecutive_memory_pressure_skips` to the captain schedule registry entry (treat missing as 0)
- [x] Add `_record_memory_pressure_cycle()` that increments the counter under `_registry_lock` and persists it
- [x] Add `_mail_admiral()` (or reuse existing Admiral-mail path) delivering via `maildeliver admiral@localhost` inside the crew container
- [x] Fire the Admiral escalation exactly once, edge-triggered, when the counter equals `GA_SPAWN_PRESSURE_ESCALATE_CYCLES`
- [x] In the captain fire path (server.py ~lines 3480–3482) catch `_MemoryPressureSkip` separately and call `_record_memory_pressure_cycle()`; keep the generic `except` for other errors
- [x] Reset `consecutive_memory_pressure_skips` to 0 on the successful-dispatch branch (where `current_task_id`/`next_fire_at` are persisted)
- [x] Apply the same memory-pressure classification to the second `immediate_dispatch_error` site in `_schedule_add` (server.py ~line 3949)

## Order templates (Raven)

- [x] Add the "spawn refused under memory pressure" branch to `academy/orders/spec-driven-development.md` (dispatch-coordination section, after the existing "If `/api/spawn` fails" sentence)
- [x] Add the equivalent memory-pressure branch to `academy/orders/independent-review.md` (dispatch phase, scoped to the four reviewer spawns)

## Tests

- [x] Unit test `_check_in_memory_pressure` (below threshold → value, at/above → None, exception → None, `None` probe → None)
- [x] Unit test `_is_memory_pressure_refusal` (memory-pressure 429/503 → True; 503-still-spawning and unrelated bodies → False)
- [x] Unit test `_record_memory_pressure_cycle` (increment, missing-field-as-0, single edge-triggered mail at the boundary, no re-mail above bound, reset on success)
- [x] Integration test (mock gateway): memory-pressure 503 sets `immediate_dispatch_error` with the `memory_pressure:` marker, does not advance `current_task_id`, and is not retried in-cycle

## Verification

- [x] Run `bash tests/run.sh --unit` and confirm green
- [x] Confirm `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` default (3) is documented wherever other `GA_*` thresholds are listed
- [x] Manual trace: no change to `_crew_api_with_recovery` recovery phases; no change to `GA_MIN_FREE_MEM_GB` crew-launch gate
