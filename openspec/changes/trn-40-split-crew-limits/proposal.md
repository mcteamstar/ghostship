## Why

`GA_MAX_CREWS` caps the total number of registered crews. A stopped crew uses
~0 RAM (paused container, idle volumes) but counts equally against the limit.
This forces operators to choose between keeping long-lived idle crews around
(useful for persistent workspaces) and protecting memory (useful for constrained
hosts). The two concerns should be addressed by separate knobs.

## What Changes

- **Rename `GA_MAX_CREWS` semantics**: it continues to exist as the cap on
  total *registered* crews (running + stopped). Default raised from 6 → 20,
  since stopped crews are essentially free.
- **Add `GA_MAX_ACTIVE_CREWS`**: new env var that caps *simultaneously running*
  containers. Checked in `_ensure_crew_running` before starting a stopped crew.
  Default: 3, reflecting ~2-3 GB active memory per crew on a typical host.
- `launch` continues to check `GA_MAX_CREWS` (total registered).
- `_ensure_crew_running` gains a new pre-start check against `GA_MAX_ACTIVE_CREWS`
  (count of containers with `status == "running"` in the registry).
- Update `docs/configuration.md` and `config/ghostship.conf.example`.
- Update the `crews()` response to include `active_crews` and `max_active_crews`
  alongside the existing `host_memory_available_gb`.

## Capabilities

### New Capabilities

_(none — this extends existing configuration)_

### Modified Capabilities

- `crew-lifecycle`: `launch` max-crews check semantics clarified; new
  `GA_MAX_ACTIVE_CREWS` check added to `_ensure_crew_running`

## Impact

- `transport/server.py` — `GA_MAX_CREWS` default change + new `GA_MAX_ACTIVE_CREWS`
  constant; ~10 lines in `_ensure_crew_running`; `crews()` response shape
- `docs/configuration.md` — new row for `GA_MAX_ACTIVE_CREWS`, updated default
  for `GA_MAX_CREWS`
- `config/ghostship.conf.example` — new commented-out line
- `transport/test_transport.py` — extend max-crews tests to cover both limits
