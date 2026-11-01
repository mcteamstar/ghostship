# TRN-296 — Fix test suite reliability

## Problem

The unit test suite has two classes of test that hang or fail in the container
environment, causing Ghost/Banshee to time out at 180 min waiting for pytest:

1. **Bash subprocess tests** (`test_portal_host.py`, marked `@slow`)  
   These spawn `bash` subprocesses and hang indefinitely inside containers.
   A band-aid `@pytest.mark.slow` marker was added to skip them when running
   with `-m "not slow"`. This is wrong: skipping tests is not fixing them.
   Moreover, TRN-294 introduced `test_portal_host_py.py` which covers the
   same logic in pure Python — the bash tests are now largely redundant.

2. **Missing `starlette` dependency** (`test_server.py`, `test_radar_server.py`)  
   Both files fail with `ModuleNotFoundError: No module named 'starlette'`
   because starlette is not installed in the test venv. These are real tests
   that should run.

## Proposed fix

- **Remove** the bash subprocess tests from `test_portal_host.py` that are
  fully covered by `test_portal_host_py.py`. Any bash tests covering
  behaviour not yet ported to Python should be ported, then removed.
- **Add** `starlette` (and `httpx` if missing) to the test requirements so
  `test_server.py` and `test_radar_server.py` pass.
- **Remove** the `@pytest.mark.slow` marker and the `slow` marker definition
  from `pytest.ini` once the above are done — it was only added as a
  workaround.
- **Verify** the full unit suite runs clean (`pytest tests/unit/`) with no
  hangs and no skips due to missing deps.

## Out of scope

- The CI `--skip-slow` flag in `run.sh` — remove once the above is verified.
- The SDD template pytest invocation (currently uses `-m "not slow"`) —
  update to drop that flag once the suite is clean.
