## 1. Extend patch_crew_config.py to support full config structure

- [ ] 1.1 Update `transport/container_scripts/patch_crew_config.py` to accept a full config dict (not just agent-scoped keys) and deep-merge all top-level sections into `config.local.json`
- [ ] 1.2 Ensure backward compatibility — existing callers passing only `agent` keys continue to work

## 2. Update _patch_crew_config in lifecycle.py

- [ ] 2.1 Extend `agent_overrides` in `_patch_crew_config` to a full `full_overrides` dict covering:
  - `stt`: `{"enabled": False}`
  - `session`: `{"eager_spawn": False, "timeout_secs": 300, "watchdog_rss_max_mb": 2000}`
  - `telemetry`: `{"beacon_enabled": False}`
  - top-level: `{"auto_update": False}`
- [ ] 2.2 Pass `full_overrides` to `patch_crew_config.py` instead of just `agent_overrides`

## 3. Add unit tests

- [ ] 3.1 In `tests/unit/test_lifecycle.py`, add tests verifying each new config section (`stt`, `session`, `telemetry`, `auto_update`) is written to `config.local.json`
- [ ] 3.2 Run `bash tests/run.sh --unit` and confirm all tests pass

## 4. Update docs

- [ ] 4.1 In `docs/configuration.md`, document the fixed headless overrides applied to every crew and explain `session.watchdog_rss_max_mb`

## 5. Validate and measure

- [ ] 5.1 Run `openspec validate "trn-127-headless-crew-memory-baseline"`
- [ ] 5.2 Deploy to vm23
- [ ] 5.3 Launch a fresh crew and measure idle RSS — confirm ~160 MB baseline (down from ~470 MB)
- [ ] 5.4 Dispatch a task and confirm it completes successfully (session spawns on demand)
- [ ] 5.5 Measure post-task RSS after 5 minutes — confirm session process has been reaped
