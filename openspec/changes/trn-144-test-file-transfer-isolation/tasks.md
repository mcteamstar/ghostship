## 1. Fix test_file_transfer.py stub isolation

- [ ] 1.1 Before the try/except stub-installation block in `test_file_transfer.py`, add a module-level snapshot of the pre-stub state for all keys that `_install_import_stubs()` writes to `sys.modules`: `httpx`, `mcp`, `mcp.server`, `mcp.server.mcpserver`, `mcp.server.mcpserver.server`, `starlette`, `starlette.applications`, `starlette.requests`, `starlette.responses`, `starlette.routing`, `uvicorn`
- [ ] 1.2 Add a `tearDownModule` function that restores each key to its pre-stub value (re-inserting the original module if it existed, removing the key entirely if it didn't)
- [ ] 1.3 Run `bash tests/run.sh --unit` and confirm zero errors in `test_recovery` and all other test files
- [ ] 1.4 Run `python3 -m unittest tests.unit.test_file_transfer` in isolation and confirm it still passes
