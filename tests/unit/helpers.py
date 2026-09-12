"""Shared test helpers for the modularised transport unit suite (TRN-85).

The ~8500-line ``test_transport.py`` is being split into one test file per
transport module (``test_registry.py``, ``test_podman.py``, ``test_files.py``,
``test_captain.py``, ``test_academy.py``, ``test_lifecycle.py``,
``test_server.py``). This module holds the pieces shared *across* those files:

* the ``server`` module handle, imported via the dependency-free bootstrap in
  ``test_file_transfer._install_import_stubs`` (so the suite runs inside a crew
  container with no ``httpx``/``mcp``/``starlette`` installed), and the
  per-module aliases (``registry``, ``podman``, ``files_mod``, ``captain_mod``,
  ``academy``, ``lifecycle``);
* mock factories used by test classes that land in more than one file.

Phase-2 migration moves genuinely cross-file mock factories here; single-cluster
helpers move with the class cluster that uses them.
"""

from __future__ import annotations

from typing import Any  # noqa: F401  (used by helpers added during migration)
from unittest.mock import MagicMock, Mock

# Reuse the dependency-free import bootstrap: importing ``server`` from
# test_file_transfer installs the stdlib stubs (httpx/mcp/starlette/uvicorn)
# on first import if the real packages are absent, then hands back the real
# ``transport.server`` module.
from tests.unit.test_file_transfer import server  # noqa: F401  (re-exported)

import transport.registry as registry  # noqa: F401  (re-exported)
import transport.podman as podman  # noqa: F401  (re-exported)
import transport.files as files_mod  # noqa: F401  (re-exported)
import transport.captain as captain_mod  # noqa: F401  (re-exported)
import transport.academy as academy  # noqa: F401  (re-exported)
import transport.lifecycle as lifecycle  # noqa: F401  (re-exported)
import transport.monitors as monitors  # noqa: F401  (re-exported, TRN-116 §8)


class Request:
    """Minimal HTTP request stub used by file-transfer and server tests.

    Shared between test_files.py and test_server.py — both need it.
    """

    def __init__(
        self,
        crew_id: str,
        path: str,
        body: bytes,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.path_params = {"crew_id": crew_id, "path": path}
        self.query_params = query_params or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body


class FakePodmanClient:
    """Podman client stand-in with a scripted ``system_info()`` memory sequence.

    Shared by ``test_podman.py`` (memory-gate / cache tests) and
    ``test_lifecycle.py`` (``ActiveCrewLimitTests`` and the memory-gate-disabled
    path drive ``_ensure_crew_running`` through it).
    """

    def __init__(self, mem_free_bytes_sequence: list[int] | None = None) -> None:
        """mem_free_bytes_sequence: list of memAvailable values to return on successive calls."""
        self._mem_sequence = mem_free_bytes_sequence or [4 * 1024**3]
        self._call_index = 0
        self.system_info_calls = 0

    def system_info(self) -> dict:
        self.system_info_calls += 1
        idx = min(self._call_index, len(self._mem_sequence) - 1)
        self._call_index += 1
        return {"host": {"memAvailable": self._mem_sequence[idx]}}

    def container_start(self, name: str) -> None:
        pass

    def container_stop(self, name: str) -> None:
        pass

    def container_is_running(self, name: str) -> bool:
        return False

    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        return "ready"

    def container_exec_stdin(
        self, container: str, cmd: list[str], stdin_data: bytes
    ) -> str:
        """Stub: record the call and return a configurable response."""
        if not hasattr(self, "_exec_stdin_calls"):
            self._exec_stdin_calls: list[tuple[str, list[str], bytes]] = []
        self._exec_stdin_calls.append((container, cmd, stdin_data))
        return getattr(self, "_exec_stdin_response", "admiral secret injected")


# ── Consolidated HTTP mocks (TRN-143 §4) ────────────────────────────────────
#
# Four independent FakeHTTP / FakeResponse definitions previously lived in
# test_recovery.py, test_monitors.py (as MockHTTPResponse), test_server.py, and
# test_file_transfer.py. Their constructor signatures diverged:
#
#   * test_recovery       FakeResponse(status_code, json_body)      + raise_for_status
#   * test_monitors       MockHTTPResponse(status_code, json_data)  (json only)
#   * test_file_transfer  FakeResponse(status_code, content, json_data, chunks)
#                         + text/read/iter_bytes/close/closed
#   * test_server         async FakeHTTP.request(...) returning Mock()
#
# The unified FakeResponse below is a superset: every keyword is optional, so a
# caller uses only the attributes it cares about. FakeHTTP is the sequential
# sync client (recovery + monitors pattern); FakeAsyncHTTP is the async proxy
# client (server pattern).


class FakeResponse:
    """Unified httpx.Response / MockHTTPResponse stand-in (TRN-143 §4).

    Superset of the four prior definitions — pass only the keywords a given
    test needs:

    * ``status_code`` / ``json_body`` (aka ``json_data``) drive ``json()`` and
      ``raise_for_status()`` (recovery, monitors).
    * ``content`` / ``chunks`` drive ``content``, ``text``, ``read()`` and
      ``iter_bytes()`` (file-transfer streaming).
    """

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        json_body: Any = None,
        json_data: Any = None,  # alias for json_body (monitors/file-transfer)
        chunks: list[bytes] | None = None,
        headers: dict | None = None,
    ) -> None:
        self.status_code = status_code
        # json_body / json_data are aliases; json_body wins when both are given.
        _json = json_body if json_body is not None else json_data
        self._json = _json if _json is not None else {}
        # file-transfer parity: default an empty body to b"{}" only when no JSON
        # payload was supplied (matches the original test_file_transfer default).
        self.content = content if (content or _json is not None) else b"{}"
        self._chunks = chunks if chunks is not None else [content]
        self.headers = headers if headers is not None else {}
        self.closed = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx2 as httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self,
            )

    def read(self) -> bytes:
        return self.content

    def iter_bytes(self):
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakeHTTP:
    """Sequential sync httpx.Client replacement (TRN-143 §4).

    Returns the scripted ``responses`` in order for ``get``/``request``; once
    exhausted it returns ``default`` (a 200/empty ``FakeResponse`` by default).
    Every requested URL is recorded in ``self.calls`` so tests that previously
    closed over a local ``http_calls`` list (monitors) can read it back.
    """

    def __init__(
        self,
        responses: list[FakeResponse] | None = None,
        default: FakeResponse | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._call_idx = 0
        self._default = default if default is not None else FakeResponse(200, json_body={})
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self._next()

    def request(self, method, url, **kwargs):
        self.calls.append(url)
        return self._next()

    def _next(self) -> FakeResponse:
        if self._call_idx < len(self._responses):
            r = self._responses[self._call_idx]
            self._call_idx += 1
            if isinstance(r, BaseException):
                raise r
            return r
        if isinstance(self._default, BaseException):
            raise self._default
        return self._default


class FakeAsyncHTTP:
    """Async httpx.AsyncClient replacement for the crew proxy handlers (TRN-143 §4).

    Records every forwarded request's headers in ``self.captured_headers`` and
    returns a ``Mock`` response. ``statuses`` scripts the status code sequence
    (e.g. ``[401, 200]`` to exercise the cookie-refresh retry); once exhausted
    the last status repeats. ``content`` / ``headers`` set the response body and
    headers on each returned Mock.
    """

    def __init__(
        self,
        statuses: list[int] | None = None,
        content: bytes = b"{}",
        headers: dict | None = None,
    ) -> None:
        self._statuses = list(statuses or [200])
        self._content = content
        self._resp_headers = headers if headers is not None else {}
        self._call_idx = 0
        self.captured_headers: list[dict] = []
        self.call_count = 0

    async def request(self, method, url, headers=None, content=None):
        self.captured_headers.append(dict(headers or {}))
        self.call_count += 1
        idx = min(self._call_idx, len(self._statuses) - 1)
        self._call_idx += 1
        resp = Mock()
        resp.status_code = self._statuses[idx]
        resp.content = self._content
        resp.headers = dict(self._resp_headers)
        return resp
