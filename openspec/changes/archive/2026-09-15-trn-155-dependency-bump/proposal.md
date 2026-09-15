# TRN-155: Dependency Uplift — mcp, croniter, httpx-ws → websockets, unittest-parallel → pytest-xdist

## Why

Four transport dependencies are outdated or owned by single individuals with no institutional backing. Two are simple pin bumps. Two require code changes — replacing `httpx-ws` (single-maintainer, 152 stars) with `websockets` (5700 stars, canonical Python WS library) and `unittest-parallel` (single-maintainer) with `pytest-xdist` (pytest-dev org, the official pytest project).

The `httpx-ws` replacement also unlocks dropping the `httpx` compatibility shim kept solely to satisfy `httpx-ws`'s transitive dependency — reducing the transport's dependency surface.

## What Changes

- **`mcp==2.0.0` → `mcp==2.2.0`** — pin bump, no code changes
- **`croniter==3.0.3` → `croniter==6.2.4`** — pin bump; our single call site (`croniter(expr, time.time()).get_next(float)`) is API-stable across all versions
- **`httpx-ws==0.7.0` → removed; `websockets>=13.0,<15.0` added** — rewrite `_handle_crew_ws_proxy` in `server.py` to use `websockets.connect()` directly rather than piggy-backing on the httpx transport layer
- **`httpx==0.28.1` → removed** — no longer needed once `httpx-ws` is gone; kept only as an `httpx-ws` transitive dep
- **`unittest-parallel==1.8.6` → removed; `pytest-xdist>=3.5.0,<4.0.0` + `pytest>=8.0.0,<9.0.0` added** — replace `python3 -m unittest_parallel` in `tests/run.sh` with `python3 -m pytest tests/e2e -n auto`

## Capabilities Affected

- `dependency-management` (new delta spec) — documents pinning policy for transport dependencies
- `crew-ui-spa-routing` (existing spec) — the WS proxy behaviour contract is unchanged; implementation detail only

## Risks

- WS proxy rewrite is the highest-risk change. The new implementation must correctly handle: upstream connection failure before client accept, bidirectional message relay, subprotocol negotiation, and clean teardown when either side closes.
- pytest-xdist changes e2e test invocation. The tests themselves are standard `unittest.TestCase` which pytest collects natively — no test changes needed.
- `httpx` removal must be verified: confirm no other transport module imports it directly (all should use `httpx2`).
