# TRN-296 — Design

## Root causes

### 1. Bash subprocess hang in containers

`test_portal_host.py` spawns bash subprocesses via `subprocess.run(["bash",
...])`. Inside the KiroCrew container the bash process hangs — likely due to
a missing tty, stdin blocking, or the container's bash not finding expected
resources. The hang is unbounded (no timeout), so pytest blocks forever.

**Fix:** Remove tests. TRN-294 already delivered `test_portal_host_py.py`
which covers all the same logic (`is_loopback`, `public_base`, `probe_base`,
`check_exposure`, `resolve_api_key`) in pure Python against the
`portal_host.py` module. Any remaining bash-only coverage (e.g. the
`portal_resolve_api_key` shell function parity) should be ported to Python
tests against `portal_host.py`'s CLI, then the bash tests deleted entirely.

The `@pytest.mark.slow` marker in `pytest.ini` and the reassignment in
`test_portal_host.py` (`needs_bash = pytest.mark.slow(needs_bash)`) should
both be removed once the bash tests are gone.

### 2. Missing starlette in test venv

`test_server.py` and `test_radar_server.py` import `starlette` (or need it
transitively). It is not listed in the test requirements. Fix: add it.

Check `requirements.txt` and `tests/requirements.txt` (or equivalent) and
add `starlette` at the pinned version used by the transport.

## Affected files

| File | Change |
|:-----|:-------|
| `tests/unit/test_portal_host.py` | Remove all `@needs_bash` tests (20+ tests); keep the pure-Python static-analysis tests at the bottom |
| `tests/unit/test_portal_host_py.py` | Augment with any coverage gaps left by removal above |
| `pytest.ini` | Remove `slow` marker definition |
| `requirements.txt` / test deps | Add `starlette` (pinned) |
| `scripts/run.sh` | Remove `-m "not slow"` from unit test invocation |

## Verification

- `pytest tests/unit/` runs to completion with no hangs, no `ModuleNotFoundError`, no skips due to missing deps
- Total test count does not decrease (pure-Python replacements cover removed bash tests)
- CI green
