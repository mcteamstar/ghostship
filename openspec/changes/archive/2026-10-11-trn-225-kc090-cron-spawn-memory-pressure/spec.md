# Spec Delta — TRN-225 Cron spawn refused under memory pressure

This is a delta spec: it states behaviour that changes relative to the current
ghostship transport and Raven order templates.

## Capability: Captain check-in dispatch under host memory pressure

### Behaviour BEFORE this change

- `_dispatch_captain_checkin()` always calls `POST /api/spawn` with no host-memory
  check of its own.
- Under KiroCrew 0.9.0 the gateway refuses that spawn when the host is under
  critical memory pressure (upstream PR #2432). The refusal is caught generically
  and stored as `result["immediate_dispatch_error"] = str(exc)`.
- The transport cannot tell a memory-pressure refusal apart from any other
  `/api/spawn` error; there is no counter, no escalation, no typed outcome.
- The Raven order templates have no memory-pressure branch. Bounded retry happens
  only as an accident of intent-marker staleness; sustained pressure skips
  check-ins silently and indefinitely with no Admiral signal.

### Behaviour AFTER this change

#### REQUIREMENT: transport probes host memory before dispatching a check-in

- Before calling `/api/spawn`, `_dispatch_captain_checkin()` SHALL read host
  available memory via `_get_host_memory_gb_cached()`.
- WHEN available memory is below `GA_RESOURCE_CRITICAL_GB`, the transport SHALL
  skip the dispatch WITHOUT calling `/api/spawn`, log the skip with reason
  `memory_pressure`, set `result["immediate_dispatch_error"]` to a string that
  begins with the stable marker `memory_pressure:`, and NOT advance
  `current_task_id`.
- WHEN the memory probe is unavailable (helper returns `None`), the transport
  SHALL proceed with the dispatch as today (fail-open: do not block the crew on a
  missing probe).

#### REQUIREMENT: transport classifies a gateway spawn refusal as memory pressure

- WHEN `/api/spawn` is attempted and the gateway refuses with a memory-pressure
  response, the transport SHALL classify that error and set
  `result["immediate_dispatch_error"]` to a string beginning with
  `memory_pressure:`.
- Classification SHALL match the gateway's memory-pressure refusal signal
  (HTTP 503/429 whose body/reason names memory pressure) and SHALL NOT be
  routed through `_crew_api_with_recovery`'s in-cycle retry phases.

#### REQUIREMENT: consecutive memory-pressure cycles are counted and escalated

- The transport SHALL maintain a per-crew `consecutive_memory_pressure_skips`
  counter in the captain schedule registry entry.
- A memory-pressure skip or refusal SHALL increment the counter; any successful
  dispatch SHALL reset it to `0`.
- WHEN the counter reaches `GA_SPAWN_PRESSURE_ESCALATE_CYCLES`, the transport
  SHALL emit exactly one Admiral-facing escalation (mail to `admiral@localhost`
  with subject `captain check-in deferred — sustained memory pressure <crew_id>`)
  and SHALL NOT re-emit on every subsequent cycle while the counter stays at or
  above the bound (edge-triggered, not level-triggered).

#### REQUIREMENT: Raven order templates recognise a memory-pressure refusal

- `spec-driven-development.md` and `independent-review.md` SHALL instruct Raven
  that a `/api/spawn` call MAY be refused for memory pressure, how to recognise
  it, that it MUST hold (write no confirmation, leave the pending intent marker
  so the dispatch is retried on a later cycle, not treat the refusal as a
  completed dispatch), and that after N consecutive refused cycles it SHALL mail
  `admiral@localhost`.

## Configuration delta

New config key (added to `transport/config.py` `TransportConfig` and its loader):

| Key | Env var | Type | Default | Meaning |
|---|---|---|---|---|
| `ga_spawn_pressure_escalate_cycles` | `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` | int | `3` | Consecutive memory-pressure check-in cycles before the transport mails the Admiral |

Reused (no change):

| Key | Default | Role in this change |
|---|---|---|
| `ga_resource_critical_gb` | `1.0` | Threshold for the pre-dispatch skip |

## Registry schema delta

The captain schedule entry (type `"captain"`) gains one additive field:

- `consecutive_memory_pressure_skips: int` — defaults to `0`/absent for existing
  rows; code MUST treat a missing field as `0`.
