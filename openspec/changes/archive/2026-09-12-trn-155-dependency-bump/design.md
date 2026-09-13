# TRN-155 Design: Dependency Uplift

## 1. Pin bumps (no code changes)

### mcp 2.0.0 → 2.2.0
Update `transport/requirements.txt`:
```
mcp[cli]==2.2.0
```
No API changes affecting ghostship. mcp 2.x already uses httpx2 natively.

### croniter 3.0.3 → 6.2.4
Update `transport/requirements.txt`:
```
croniter==6.2.4
```
Single call site in `transport/registry.py`:
```python
from croniter import croniter as _croniter
job["next_fire_at"] = _croniter(job["cron_expr"], time.time()).get_next(float)
```
This API is unchanged across all versions tested (3.0.3 through 6.2.4).

---

## 2. httpx-ws → websockets + drop httpx shim

### New dependency
```
websockets>=13.0,<15.0
```

### Remove
```
httpx==0.28.1        # was: kept for httpx-ws compatibility
httpx-ws==0.7.0
wsproto              # was: transitive from httpx-ws
```

### WS proxy rewrite (`transport/server.py`)

The current proxy (`_handle_crew_ws_proxy`) uses `httpx_ws.aconnect_ws` which connects over an existing httpx async client. The new implementation uses `websockets.connect()` directly.

**Current shape:**
```python
from httpx_ws import aconnect_ws as _aconnect_ws
async with _aconnect_ws(upstream_url, _async_http, headers=..., subprotocols=...) as upstream:
    ...
```

**New shape:**
```python
import websockets
async with websockets.connect(
    upstream_url,
    additional_headers=handshake_headers,
    subprotocols=subprotocols or None,
) as upstream:
    await ws.accept(subprotocol=upstream.subprotocol)
    async def _client_to_upstream():
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                await upstream.close()
                return
            if msg.get("text") is not None:
                await upstream.send(msg["text"])
            elif msg.get("bytes") is not None:
                await upstream.send(msg["bytes"])

    async def _upstream_to_client():
        async for message in upstream:
            if isinstance(message, str):
                await ws.send_text(message)
            else:
                await ws.send_bytes(message)

    done, pending = await asyncio.wait(
        {asyncio.create_task(_client_to_upstream()),
         asyncio.create_task(_upstream_to_client())},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
```

**Key differences from httpx-ws:**
- `websockets.connect()` raises `websockets.exceptions.WebSocketException` on connection failure (not httpx errors) — the outer `except Exception` in `_handle_crew_ws_proxy` still catches these
- Messages are received via async iteration (`async for message in upstream`) rather than `upstream.receive()` — simpler and more idiomatic
- No `wsproto` event dispatch needed — websockets returns `str` or `bytes` directly
- `upstream.subprotocol` gives the negotiated subprotocol after connect

**The `_async_http` (module-level AsyncClient) dependency:** The WS proxy currently shares the httpx2 async client for connection. With websockets the connection is independent. This is fine — websockets manages its own connection pool. The `_async_http` client remains for all non-WS transport calls.

**URL scheme:** `websockets.connect` requires `ws://` or `wss://` not `http://`. The upstream URL must be rewritten: `upstream_ws_url` is already constructed with `ws://` scheme in the existing code (search for `upstream_ws_url` in server.py) — verify this holds.

**Import guard:** Keep the lazy import pattern:
```python
try:
    import websockets as _websockets
    import websockets.exceptions as _ws_exceptions
except ImportError:
    _websockets = None
    _ws_exceptions = None
```

### Verify no direct httpx imports remain
Run: `grep -r "^import httpx\b\|^from httpx " transport/` — should return empty after removing httpx-ws.

---

## 3. unittest-parallel → pytest-xdist

### New dependencies (test runner only, not in transport image)
```
pytest>=8.0.0,<9.0.0
pytest-xdist>=3.5.0,<4.0.0
```

These go in `transport/requirements.txt` (the test runner installs from there) or a separate `tests/requirements.txt` if one exists. Check current structure — if all deps are in one file, add with a `# test runner only` comment.

### `tests/run.sh` change

Replace the `unittest_parallel` block in the `e2e` case:
```bash
# Before:
if python3 -c "import unittest_parallel" 2>/dev/null; then
  run_category e2e python3 -m unittest_parallel -s tests/e2e -p "test_*.py" -t .
else
  run_category e2e python3 -m unittest discover -s tests/e2e -p "test_*.py" -t .
fi

# After:
run_category e2e python3 -m pytest tests/e2e -p "test_*.py" -n auto
```

pytest collects `unittest.TestCase` subclasses natively — no changes to test files.

For the unit test runner, consider also migrating to pytest for consistency:
```bash
# Before:
run_category unit python3 -m unittest discover -s tests/unit -p "test_*.py" -t .

# After:
run_category unit python3 -m pytest tests/unit -p "test_*.py"
```
This is optional but desirable — single test runner for the whole suite.

---

## 4. Verification

1. `bash tests/run.sh --unit` — all unit tests pass
2. `bash tests/run.sh --e2e` against academy — all e2e tests pass, WS proxy exercised
3. Manual: open a crew dashboard in the browser and verify WS connection works (live session)
4. `grep -r "^import httpx\b\|^from httpx " transport/` — empty (no stray httpx imports)
