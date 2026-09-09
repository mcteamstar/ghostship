## 1. Create constants.py

- [ ] 1.1 Create `transport/constants.py` with all container-side constants: `CREW_GATEWAY_PORT`, `CREW_CONTAINER_PREFIX`, `CREW_VOLUME_PREFIX`, `CREW_HOME_VOLUME_PREFIX`, `GA_PORTSIDE_NETWORK`, `GA_STARBOARD_NETWORK`, `PERSONA_NAMES`, `SCRIPTS_DIR`
- [ ] 1.2 Verify `transport/constants.py` has zero transport imports (no imports from any other `transport.*` module)

## 2. Update lifecycle.py

- [ ] 2.1 Replace the constant declarations in `lifecycle.py` with `from transport.constants import ...`
- [ ] 2.2 Preserve all existing re-exports (e.g. `GA_PORTSIDE_NETWORK = GA_PORTSIDE_NETWORK`) as pass-through imports so callers of `lifecycle.*` are unaffected

## 3. Update server.py

- [ ] 3.1 Remove duplicate constant declarations in `server.py` (those already imported from `lifecycle` can stay as-is if using lifecycle re-exports; remove any that are independently redeclared)

## 4. Update podman.py and captain.py

- [ ] 4.1 Remove `CREW_CONTAINER_PREFIX` declaration from `podman.py`, import from `transport.constants`
- [ ] 4.2 Remove `SCRIPTS_DIR` declaration from `captain.py`, import from `transport.constants`

## 5. Update monitors.py

- [ ] 5.1 Remove the `bind_lifecycle()` injection of `CREW_GATEWAY_PORT` from `monitors.py`
- [ ] 5.2 Add `from transport.constants import CREW_GATEWAY_PORT` at module level in `monitors.py`
- [ ] 5.3 Verify `bind_lifecycle()` still works for the remaining injected lifecycle functions (`_ensure_crew_running`, `_crew_api`, etc.) — only the constant injection is removed

## 6. Remove files.py lazy-import dead code

- [ ] 6.1 Confirm no test path exercises the `server.py` fallback in `_crew_helpers()` (grep for `_crew_helpers` in tests, verify the server fallback branch is never hit)
- [ ] 6.2 Remove the `_crew_helpers()` function from `files.py`
- [ ] 6.3 Add `from transport.lifecycle import _ensure_crew_running, _require_crew` at module load time in `files.py`
- [ ] 6.4 Replace all call sites of `_crew_helpers()[0]` and `_crew_helpers()[1]` with direct references to `_ensure_crew_running` and `_require_crew`

## 7. Verify and commit

- [ ] 7.1 Run the full unit test suite (`python3 -m unittest discover -s tests/unit -p "test_*.py" -t .`) — confirm 804 tests pass, 0 new errors
- [ ] 7.2 Audit any tests that patch `lifecycle.CREW_GATEWAY_PORT`, `server.CREW_GATEWAY_PORT`, or similar — update patch targets to `transport.constants.CREW_GATEWAY_PORT` where needed
- [ ] 7.3 Commit: `refactor: introduce constants.py and remove files.py lazy-import dead code`
