# TRN-296 — Tasks

## T1 — Fix starlette missing dependency

- [ ] 1.1 Find where test dependencies are declared (requirements.txt, tests/requirements.txt, setup.cfg, pyproject.toml)
- [ ] 1.2 Identify the pinned starlette version used by transport/
- [ ] 1.3 Add starlette (and httpx if also missing) to test deps at that version
- [ ] 1.4 Verify `pytest tests/unit/test_server.py tests/unit/test_radar_server.py` passes with no ModuleNotFoundError

## T2 — Remove redundant bash subprocess tests

- [ ] 2.1 Audit `test_portal_host.py` — list every `@needs_bash` test and its equivalent in `test_portal_host_py.py`
- [ ] 2.2 Port any coverage gaps to `test_portal_host_py.py` (pure Python, against portal_host.py CLI)
- [ ] 2.3 Delete all `@needs_bash` tests from `test_portal_host.py`
- [ ] 2.4 Remove the `needs_bash` and `PORTAL_LIB`/`BASH` setup from `test_portal_host.py`
- [ ] 2.5 Verify `pytest tests/unit/test_portal_host.py tests/unit/test_portal_host_py.py` passes

## T3 — Remove slow marker band-aid

- [ ] 3.1 Remove `slow` marker definition from `pytest.ini`
- [ ] 3.2 Remove `-m "not slow"` from `scripts/run.sh` unit test invocation
- [ ] 3.3 Verify `scripts/run.sh --unit` passes clean (no hangs, no skips)

## T4 — Full suite verification

- [ ] 4.1 Run `pytest tests/unit/` to completion — confirm no hangs, no ModuleNotFoundError
- [ ] 4.2 Confirm test count is equal or greater vs pre-change baseline
- [ ] 4.3 Run `bash -n bin/install.sh` — still passes
- [ ] 4.4 Check off all tasks and commit
