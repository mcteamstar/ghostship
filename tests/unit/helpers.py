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
