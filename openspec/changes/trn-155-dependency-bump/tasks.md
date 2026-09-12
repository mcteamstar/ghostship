# TRN-155 Tasks: Dependency Uplift

## Phase 1 — Pin bumps (no code changes)

- [x] T1. In `transport/requirements.txt`, bump `mcp[cli]==2.0.0` → `mcp[cli]==2.2.0`
- [x] T2. In `transport/requirements.txt`, bump `croniter==3.0.3` → `croniter==6.2.4`
- [x] T3. Run `bash tests/run.sh --unit` — confirm pass

## Phase 2 — httpx-ws → websockets

- [ ] T4. In `transport/requirements.txt`:
  - Remove `httpx==0.28.1` and its compatibility comment
  - Remove `httpx-ws==0.7.0`
  - Add `websockets>=13.0,<15.0`
- [ ] T5. In `transport/server.py`, update the lazy import block (currently imports `aconnect_ws`, `_WsCloseConnection`, etc.) to import `websockets` and `websockets.exceptions` instead
- [ ] T6. Rewrite `_handle_crew_ws_proxy` to use `websockets.connect()`:
  - Replace `async with _aconnect_ws(...)` with `async with websockets.connect(...)`
  - Replace `upstream.receive()` call + wsproto event dispatch with `async for message in upstream`
  - Set `upstream.subprotocol` on `ws.accept()` call
  - Keep the outer `except Exception` error handler and 1011 close-on-failure logic unchanged
- [ ] T7. Verify upstream WS URL uses `ws://` scheme (search `upstream_ws_url` in server.py — should already be correct)
- [ ] T8. Run `grep -r "^import httpx\b\|^from httpx " transport/` — must return empty
- [ ] T9. Run `bash tests/run.sh --unit` — confirm pass

## Phase 3 — unittest-parallel → pytest-xdist

- [ ] T10. In `transport/requirements.txt`, remove `unittest-parallel==1.8.6`; add `pytest>=8.0.0,<9.0.0` and `pytest-xdist>=3.5.0,<4.0.0` with `# test runner only` comment
- [ ] T11. In `tests/run.sh`, replace the `unittest_parallel` conditional block with `python3 -m pytest tests/e2e -p "test_*.py" -n auto`
- [ ] T12. In `tests/run.sh`, replace the unit test `python3 -m unittest discover` with `python3 -m pytest tests/unit -p "test_*.py"` (optional consistency migration)
- [ ] T13. Run `bash tests/run.sh --unit` — confirm pass

## Phase 4 — E2E + manual verification

- [ ] T14. Deploy to academy (`./deploy.sh academy`)
- [ ] T15. Run `bash tests/run.sh --e2e` against academy — confirm pass
- [ ] T16. Open a crew dashboard in the browser and exercise the WS connection — verify live session works
- [ ] T17. Update `transport/requirements.txt` comment block if any stale comments reference removed packages
