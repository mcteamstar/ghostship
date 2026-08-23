## 1. Transport changes

- [ ] 1.1 Change `GA_MAX_CREWS` default from `"6"` to `"20"` in `transport/server.py`
- [ ] 1.2 Add `GA_MAX_ACTIVE_CREWS = int(os.environ.get("GA_MAX_ACTIVE_CREWS", "3"))` module-level constant
- [ ] 1.3 In `_ensure_crew_running`, before starting a stopped container: count `status == "running"` entries in the registry; if count >= `GA_MAX_ACTIVE_CREWS > 0`, raise `CrewUnresponsiveError` with a clear message
- [ ] 1.4 Update `crews()` response to include `active_crews` (int) and `max_active_crews` (int) fields
- [ ] 1.5 Update the error message in `launch()` to say "registered crew limit" rather than generic "Max crews"

## 2. Docs and config

- [ ] 2.1 Add `GA_MAX_ACTIVE_CREWS` row to `docs/configuration.md` (default: 3, description, note that 0 disables it)
- [ ] 2.2 Update `GA_MAX_CREWS` row in `docs/configuration.md` to reflect new default of 20 and clarify it counts registered (running + stopped) crews
- [ ] 2.3 Add commented `GA_MAX_ACTIVE_CREWS=3` line to `config/ghostship.conf.example`
- [ ] 2.4 Update `GA_MAX_CREWS` comment in `config/ghostship.conf.example` to reflect new default

## 3. Tests

- [ ] 3.1 Add test: `_ensure_crew_running` raises when `GA_MAX_ACTIVE_CREWS` running crews exist
- [ ] 3.2 Add test: `_ensure_crew_running` succeeds when active count is below limit
- [ ] 3.3 Add test: `GA_MAX_ACTIVE_CREWS=0` bypasses the active limit check
- [ ] 3.4 Add test: already-running crew bypasses the active limit check (not double-counted)
- [ ] 3.5 Update existing `MaxCrewsTests` to reflect new `GA_MAX_CREWS` default of 20
- [ ] 3.6 Add test: `crews()` response includes `active_crews` (int) and `max_active_crews` (int) fields

## 4. Validate and verify

- [ ] 4.1 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all tests pass
- [ ] 4.2 Run `openspec validate --specs` — no validation errors
