# Design

## Context

The existing test suite uses a stub `starlette` in `conftest.py`, a `FakePodmanClient`
in `tests/fakes.py` (or inline in conftest), and dependency injection patterns
(handlers receive a podman client via function argument, not via module globals). All
new tests must follow this established pattern — no `unittest.mock.patch` on module
globals, no live Podman socket required.

## Goals / Non-Goals

**Goals:**
- Add test_podman.py and test_tools.py (new files)
- Extend test_lifecycle.py, test_captain_engine.py, test_server.py, test_files.py, test_academy.py
- Verify FakePodmanClient interface parity
- Keep tests runnable without a live transport or Podman socket

**Non-Goals:**
- 100% line coverage (diminishing returns on generated/trivial paths)
- Changing runtime transport code
- E2E tests (separate suite)

## Decisions

### D1: test_podman.py — mock via responses/httpx mock, not real socket

PodmanClient uses httpx with a `unix://` transport. Use `respx` (already in the test
venv) or `unittest.mock.patch` on `httpx.Client.send` to intercept HTTP calls.
This avoids requiring a real Podman socket in CI.

Pattern:
```python
import respx, httpx

@respx.mock
def test_container_create():
    respx.post("/containers/create").mock(
        return_value=httpx.Response(201, json={"Id": "abc123"})
    )
    client = PodmanClient(socket_path="/fake.sock")
    result = client.container_create({"Image": "test"})
    assert result["Id"] == "abc123"
```

FakePodmanClient interface parity test: iterate `PodmanClient.__dict__` for all
public methods and assert each exists on `FakePodmanClient` with the same signature
(using `inspect.signature`).

### D2: test_tools.py — use FakePodmanClient + in-memory registry

The existing test pattern in `test_fleet.py` (written in TRN-97) shows how to
import `_handle_api_crews_get` and call it with a stub Request. Use the same approach
for tools: call the tool functions directly with a pre-populated in-memory registry
and FakePodmanClient.

For `nuke()`, `dispatch()`, `schedule()`, etc. — these are top-level functions in
`transport/tools.py` that read from `registry` and `_get_podman()`. The existing
approach patches `_get_podman` to return a FakePodmanClient and pre-populates
the module-level `registry` before the call.

### D3: test_lifecycle.py extensions — focus on _reconcile_registry and _reseed_crew_schedules

These are the two highest-value targets. Use a fresh in-memory registry (no file I/O)
populated with test crew entries. Call the functions directly (they accept registry
as a parameter or via the module-level `registry` singleton — check the actual
signature during implementation and use whichever the function supports).

### D4: test_captain_engine.py — add 8 targeted tests

Follow the existing pattern in `test_captain_engine.py`. For memory pressure tests,
patch `_get_host_memory_gb_cached` to return a value below `GA_RESOURCE_CRITICAL_GB`.
For the dispatch tests, patch `_crew_api` to return controlled responses.

### D5: test_server.py, test_files.py, test_academy.py — targeted additions only

Each gets the minimum tests needed to cover the named gaps. Prefer 3–5 focused tests
per file over broad coverage sweeps.

## Risks / Trade-offs

- `respx` may not be in the venv — check first; fall back to `unittest.mock.patch`
  on `httpx.Client.send` if needed.
- `registry` singleton makes test isolation tricky — use `registry._reg.clear()` +
  `registry._reg.update(fresh_data)` in setUp/tearDown rather than importing a
  separate instance.
