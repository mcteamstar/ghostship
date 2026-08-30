## Prerequisites

- [x] 0.1 TRN-71 fully landed — `transport/lifecycle.py` committed, 421 unit tests passing

## 1. Extract academy.py

- [ ] 1.1 Create `transport/academy.py` with: `COMPOSITION_REGISTRY`, `_load_composition_registry`, `_resolve_composition`, `_resolve_manifest_path`, `_resolve_image`, `_load_crew_manifest`, `_manifest_selects`, `_substitute_env_vars`, `_validate_academy`
- [ ] 1.2 Update `transport/lifecycle.py` — add try/except import from `academy`; remove the moved definitions; keep any calls to academy functions via the imported names
- [ ] 1.3 Update `transport/server.py` — add try/except import from `academy` for `COMPOSITION_REGISTRY` and any other names server reads directly; update the existing dual-patch workaround comments if needed (do not change test files)
- [ ] 1.4 Verify no circular imports:
  ```bash
  python3 -c "import transport.academy; import transport.lifecycle; import transport.server; print('OK')"
  ```
- [ ] 1.5 Run `bash tests/run.sh --unit` — all 421 tests pass
- [ ] 1.6 Commit: `refactor: extract academy.py from lifecycle.py`

## 2. Verification

- [ ] 2.1 Confirm `transport/academy.py` exists and contains all 9 extracted symbols
- [ ] 2.2 Confirm `lifecycle.py` line count is ~1500 (down from ~1842)
- [ ] 2.3 Confirm no `patch.object(lifecycle, "COMPOSITION_REGISTRY"` or `patch.object(lifecycle, "_validate_academy"` in tests — these should now be `patch.object(academy, ...)` or dual-patched pending TRN-85
  ```bash
  grep -n "lifecycle.*COMPOSITION_REGISTRY\|lifecycle.*_validate_academy\|lifecycle.*_load_crew_manifest" tests/unit/test_transport.py | head -20
  ```
  Note: dual-patches targeting both `lifecycle` and `server` for these names are acceptable until TRN-85 — just flag them in a comment
- [ ] 2.4 Run integration tests: `bash tests/run.sh --integration` — all pass
- [ ] 2.5 Deploy to vm23 and run e2e smoke test
