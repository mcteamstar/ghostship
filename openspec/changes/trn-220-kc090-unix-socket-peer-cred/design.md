# Design — TRN-220 Internal-API Peer-Cred Compatibility

## Source grounding

All line numbers are approximate and against the repo state read on
2026-10-11 (`transport/lifecycle.py` is ~172 KB; symbol anchors given so the
reviewer can relocate them if the file shifts).

### The single REST entry point: `_crew_api`

`transport/lifecycle.py` (≈L346):

```python
def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    r = _http.request(
        method, f"{url}{path}",
        headers={"Cookie": _crew_cookie(crew), "Origin": url},
        **kw,
    )
    r.raise_for_status()
    return r.json()
```

with helpers (≈L301):

```python
def _crew_url(crew: dict) -> str:
    return f"http://{crew['container']}:{CREW_GATEWAY_PORT}"

def _crew_cookie(crew: dict) -> str:
    return f"mc_token_{CREW_GATEWAY_PORT}={crew['cookie']}"
```

This is the only place the transport host builds a request to a crew gateway.
It sends `Cookie` + `Origin` and nothing else auth-bearing — the external
cookie path, which 0.9.0 does **not** peer-cred-gate. **No change to the call
itself is required.** The design makes the "cookie only" property enforced
rather than incidental.

### Why the internal path is never hit from the transport host

1. **Container scripts don't use REST.** Every file in
   `transport/container_scripts/` (`inject_auth.py`, `read_auth.py`,
   `check_gateway_ready.py`, `patch_crew_config.py`, `inject_policy.py`, …) is
   invoked via `podman.container_exec()` and operates on the local SQLite DB /
   filesystem *inside* the container. E.g. `inject_auth.py::inject_auth()`:

   ```python
   conn = sqlite3.connect(db_path)
   conn.executemany(
       "INSERT OR REPLACE INTO auth_kv (key, value) VALUES (?, ?)", rows)
   ```

   No HTTP, no `X-Internal-Secret`. The peer-cred check is a no-op for them.

2. **Crew members use the cookie path.** `transport/captain.py`
   `_RAVEN_GATEWAY_ORIENTATION` (≈L53) instructs Raven verbatim:

   > Authenticate using the dashboard session cookie at
   > `/home/kirocrew/.kiro/crew/.dashboard_cookie` … send it as
   > `Cookie: mc_token_5476=<value>` … **Do NOT send X-Internal-Secret or
   > X-Session-Key alongside the cookie — either header overrides to the
   > internal auth path and breaks the request.**

   The loopback-bound cookie Raven uses is minted by
   `_mint_internal_cookie()` (≈L1336), which runs the mint + exchange **inside**
   the container (`curl http://localhost:5476/?token=...`) so the cookie binds
   to `127.0.0.1`. That solves the IP-mismatch check and keeps Raven on the
   cookie path. `server.py` (≈L3164) writes this `internal_cookie` into
   `.dashboard_cookie` before each captain dispatch.

   Even if Raven *did* use the internal-secret path, she runs inside the
   container as `kirocrew` — the same UID as the gateway — so the peer-cred
   check would still pass. The transport host is the only context where the
   UID differs, and the transport host never sends the internal headers.

## Implementation

### 1. Pin the header contract in `_crew_api` (defensive, no behaviour change)

Make the "cookie + origin only" property explicit so a casual edit that adds a
header is visible in review. Build the header dict as a named local and assert
the forbidden keys are absent in a way that is cheap and self-documenting:

```python
_FORBIDDEN_INTERNAL_HEADERS = ("X-Internal-Secret", "X-Session-Key")

def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    headers = {"Cookie": _crew_cookie(crew), "Origin": url}
    # TRN-220: the transport host authenticates on the external cookie path.
    # The internal-secret path is peer-cred-gated in KiroCrew 0.9.0 (PR #2424)
    # and would be rejected from the transport host's UID. Never add these.
    caller_headers = kw.pop("headers", None)
    if caller_headers:
        for h in _FORBIDDEN_INTERNAL_HEADERS:
            if h in caller_headers:
                raise ValueError(
                    f"TRN-220: {h} must not be sent on the transport cookie path"
                )
        headers.update(caller_headers)
    r = _http.request(method, f"{url}{path}", headers=headers, **kw)
    r.raise_for_status()
    return r.json()
```

Note: this also safely handles any current/future caller that passes
`headers=` through `**kw` (today none do), merging them while rejecting the
forbidden pair. If a reviewer prefers zero behaviour change, the `caller_headers`
merge can be dropped and only the comment + constant retained; the regression
test below still protects the invariant.

### 2. Regression test

Add `transport/tests/test_trn220_crew_api_headers.py` (create the `tests/`
package if absent):

```python
from unittest.mock import MagicMock, patch
from transport import lifecycle

def test_crew_api_sends_cookie_path_only():
    crew = {"container": "crew-x", "cookie": "abc"}
    captured = {}
    fake = MagicMock()
    fake.json.return_value = {}
    def _req(method, url, headers=None, **kw):
        captured["headers"] = headers
        return fake
    with patch.object(lifecycle, "_http") as http:
        http.request.side_effect = _req
        lifecycle._crew_api(crew, "GET", "/api/spawn")
    assert "Cookie" in captured["headers"]
    assert "Origin" in captured["headers"]
    assert "X-Internal-Secret" not in captured["headers"]
    assert "X-Session-Key" not in captured["headers"]
```

### 3. Verification against the 0.9.0 image

Before accepting the change, confirm the cookie path still authenticates on
`0.9.0-insider.4`. Launch a crew on the pinned image and exercise a cookie-auth
REST call end-to-end (e.g. a `GET /api/spawn` list via `_crew_api`, or Raven's
`spawn list`). Confirm it returns 2xx. This is the empirical check behind the
research report's "safe today but needs verification" verdict.

## Risks and non-goals

- **Non-goal:** modifying KiroCrew's peer-cred implementation. That lives in the
  gateway image, not ghostship.
- **Risk:** a future feature that needs the internal-secret path from the
  transport host. The regression test turns that into a loud CI failure with a
  message pointing at TRN-220, which is the intended outcome — such a feature
  must instead run inside the container or use the cookie path.
- **Low effort:** this is a comment, a constant, one small guard, and one unit
  test; no container rebuild and no config change.
