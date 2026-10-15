"""Shared test fakes for the ghostship transport unit suite.

Design principle: fakes implement the same interface as their real counterparts
(ContainerRuntime / PodmanClient) without using ``unittest.mock.Mock()``.
They record calls and return scripted responses, giving tests precise control
without import-path coupling.

Usage:

    from tests.fakes import FakePodmanClient, FakeArchiveResponse

    podman = FakePodmanClient()
    podman.archive_responses["/home/kirocrew/..."] = b"...tar bytes..."
    result = some_function_under_test(podman, container="gs-abc123")
"""

from __future__ import annotations

import io
import tarfile
from typing import Any


# ── FakeArchiveResponse ───────────────────────────────────────────────────────

class FakeArchiveResponse:
    """Minimal stand-in for the httpx.Response returned by container_archive_get.

    Provides iter_bytes() and close() as required by _read_sentinel_file /
    _read_mail_subjects_archive callers.
    """

    def __init__(self, tar_bytes: bytes) -> None:
        self._bytes = tar_bytes
        self._pos = 0
        self.closed = False

    def iter_bytes(self, chunk_size: int = 65536):
        offset = 0
        while offset < len(self._bytes):
            yield self._bytes[offset:offset + chunk_size]
            offset += chunk_size

    def close(self) -> None:
        self.closed = True


def _build_tar_with_file(filename: str, content: bytes) -> bytes:
    """Build a minimal in-memory tar archive containing one file.

    Used by FakePodmanClient to simulate container_archive_get returning
    the sentinel file or any other single-file archive.
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:") as tf:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


# ── FakePodmanClient ──────────────────────────────────────────────────────────

class FakePodmanClient:
    """Complete implementation of the ContainerRuntime interface.

    All abstract methods from ContainerRuntime are implemented. No
    ``unittest.mock.Mock()`` is used — every method either returns a scripted
    response or records the call for later assertion.

    Scripted responses are set as dict entries before the test:

        podman = FakePodmanClient()
        # Script container_exec to return specific output:
        podman.exec_responses["mycontainer:rm:-f:/path"] = ""
        # Script container_archive_get to return a tar with a sentinel file:
        podman.set_archive_file(
            container="gs-abc123",
            path="/home/kirocrew/workplace/kirocrew-workspace/.captain_done",
            content=b"rewrite=complete\\n",
        )

    Recorded calls are stored in ``self.calls`` as a list of
    ``(method_name, args...)`` tuples.
    """

    def __init__(
        self,
        *,
        mem_free_bytes: int = 4 * 1024**3,
        containers: dict[str, dict] | None = None,
    ) -> None:
        """
        Args:
            mem_free_bytes: Value returned by system_info()["host"]["memAvailable"].
            containers: Pre-populated container state dict mapping name →
                {"running": bool, "inspect": {...}}.
        """
        self._mem_free_bytes = mem_free_bytes
        # Container state: {name: {"running": bool, "inspect": {...}}}
        self._containers: dict[str, dict] = containers or {}
        # Scripted exec responses: key is "<container>:<cmd_joined>" or just
        # "<container>" for a catch-all, value is the string to return.
        self.exec_responses: dict[str, str] = {}
        # Scripted exec_checked responses (same key format)
        self.exec_checked_responses: dict[str, str] = {}
        # Scripted archive_get responses: {(container, path): bytes}
        self._archive_responses: dict[tuple[str, str], bytes] = {}
        # Whether archive_get should raise RuntimeError for a (container, path)
        self._archive_errors: dict[tuple[str, str], Exception] = {}
        # Calls log: list of (method_name, *positional_args)
        self.calls: list[tuple[str, Any, ...]] = []
        # Volumes: set of volume names
        self._volumes: set[str] = set()
        # Secrets: {name: bytes}
        self._secrets: dict[str, bytes] = {}
        # Networks: set of network names
        self._networks: set[str] = set()
        # Container networks: {container_name: set(network_names)}
        self._container_networks: dict[str, set[str]] = {}

    # ── Scripting helpers ─────────────────────────────────────────────────────

    def set_archive_file(
        self,
        container: str,
        path: str,
        content: bytes,
        filename: str | None = None,
    ) -> None:
        """Script container_archive_get to return a single-file tar for (container, path)."""
        fname = filename if filename is not None else path.split("/")[-1]
        self._archive_responses[(container, path)] = _build_tar_with_file(fname, content)

    def set_archive_error(self, container: str, path: str, exc: Exception) -> None:
        """Script container_archive_get to raise exc for (container, path)."""
        self._archive_errors[(container, path)] = exc

    def set_exec_response(self, container: str, cmd: list[str], output: str) -> None:
        """Script container_exec to return output when container runs cmd."""
        key = f"{container}:{':'.join(cmd)}"
        self.exec_responses[key] = output

    def set_exec_checked_response(
        self, container: str, cmd: list[str], output: str
    ) -> None:
        """Script container_exec_checked to return output when container runs cmd."""
        key = f"{container}:{':'.join(cmd)}"
        self.exec_checked_responses[key] = output

    def add_container(
        self,
        name: str,
        *,
        running: bool = True,
        inspect: dict | None = None,
    ) -> None:
        """Register a container so container_exists / container_is_running return True."""
        self._containers[name] = {
            "running": running,
            "inspect": inspect or {"Name": name, "State": {"Status": "running" if running else "stopped"}},
        }

    # ── ContainerRuntime interface implementation ─────────────────────────────

    def container_create(
        self,
        name: str,
        image: str,
        env: dict,
        network: str,
        workspace_volume: str,
        home_volume: str,
        secrets: list[dict] | None = None,
    ) -> dict:
        self.calls.append(("container_create", name, image, network))
        self._containers[name] = {"running": False, "inspect": {"Name": name, "State": {"Status": "created"}}}
        return {"Id": name}

    def container_start(self, name: str) -> None:
        self.calls.append(("container_start", name))
        if name in self._containers:
            self._containers[name]["running"] = True
            self._containers[name]["inspect"]["State"]["Status"] = "running"

    def container_stop(self, name: str) -> None:
        self.calls.append(("container_stop", name))
        if name in self._containers:
            self._containers[name]["running"] = False
            self._containers[name]["inspect"]["State"]["Status"] = "stopped"

    def container_remove(self, name: str) -> None:
        self.calls.append(("container_remove", name))
        self._containers.pop(name, None)

    def container_inspect(self, name: str) -> dict:
        self.calls.append(("container_inspect", name))
        if name not in self._containers:
            raise RuntimeError(f"container_inspect: no such container {name!r}")
        return self._containers[name]["inspect"]

    def container_exists(self, name: str) -> bool:
        self.calls.append(("container_exists", name))
        return name in self._containers

    def container_is_running(self, name: str) -> bool:
        self.calls.append(("container_is_running", name))
        entry = self._containers.get(name)
        return entry is not None and bool(entry.get("running", False))

    def container_exec(
        self, name: str, cmd: list[str], env: dict | None = None
    ) -> str:
        self.calls.append(("container_exec", name, cmd))
        key = f"{name}:{':'.join(cmd)}"
        if key in self.exec_responses:
            return self.exec_responses[key]
        # Catch-all by container name
        if name in self.exec_responses:
            return self.exec_responses[name]
        return ""

    def container_exec_checked(
        self, name: str, cmd: list[str], env: dict | None = None
    ) -> str:
        self.calls.append(("container_exec_checked", name, cmd))
        key = f"{name}:{':'.join(cmd)}"
        if key in self.exec_checked_responses:
            return self.exec_checked_responses[key]
        if name in self.exec_checked_responses:
            return self.exec_checked_responses[name]
        return ""

    def container_exec_stdin(
        self, container: str, cmd: list[str], stdin_data: bytes
    ) -> str:
        self.calls.append(("container_exec_stdin", container, cmd, stdin_data))
        key = f"{container}:{':'.join(cmd)}"
        if key in self.exec_responses:
            return self.exec_responses[key]
        if container in self.exec_responses:
            return self.exec_responses[container]
        return ""

    def container_archive_put(
        self, name: str, workspace_path: str, tar_body: bytes
    ) -> None:
        self.calls.append(("container_archive_put", name, workspace_path, len(tar_body)))

    def container_archive_get(
        self, name: str, workspace_path: str
    ) -> FakeArchiveResponse:
        self.calls.append(("container_archive_get", name, workspace_path))
        key = (name, workspace_path)
        if key in self._archive_errors:
            raise self._archive_errors[key]
        if key in self._archive_responses:
            return FakeArchiveResponse(self._archive_responses[key])
        # Return an empty (but valid) tar archive by default
        raise RuntimeError(
            f"FakePodmanClient: no archive scripted for container={name!r} "
            f"path={workspace_path!r}"
        )

    def volume_create(self, name: str) -> None:
        self.calls.append(("volume_create", name))
        self._volumes.add(name)

    def volume_remove(self, name: str) -> None:
        self.calls.append(("volume_remove", name))
        self._volumes.discard(name)

    def secret_create(self, name: str, data: bytes) -> None:
        self.calls.append(("secret_create", name))
        self._secrets[name] = data

    def secret_remove(self, name: str) -> None:
        self.calls.append(("secret_remove", name))
        self._secrets.pop(name, None)

    def worker_run(
        self, volume_name: str, cmd: list[str], timeout: float = 60.0
    ) -> bytes:
        self.calls.append(("worker_run", volume_name, cmd))
        return b""

    def volume_name_for_crew(self, crew_id: str) -> str:
        return f"gs-vol-{crew_id}"

    def network_create(self, name: str) -> None:
        self.calls.append(("network_create", name))
        self._networks.add(name)

    def network_connect(self, container: str, network: str) -> None:
        self.calls.append(("network_connect", container, network))
        self._container_networks.setdefault(container, set()).add(network)

    def network_disconnect(self, container: str, network: str) -> None:
        self.calls.append(("network_disconnect", container, network))
        if container in self._container_networks:
            self._container_networks[container].discard(network)

    def network_rm(self, name: str) -> None:
        self.calls.append(("network_rm", name))
        self._networks.discard(name)

    def container_networks(self, container: str) -> list[str]:
        self.calls.append(("container_networks", container))
        return list(self._container_networks.get(container, set()))

    def system_info(self) -> dict:
        self.calls.append(("system_info",))
        return {"host": {"memAvailable": self._mem_free_bytes}}

    # ── call inspection helpers ───────────────────────────────────────────────

    def calls_for(self, method: str) -> list[tuple]:
        """Return all recorded calls for a given method name."""
        return [c for c in self.calls if c[0] == method]

    def was_called(self, method: str) -> bool:
        """Return True if method was called at least once."""
        return any(c[0] == method for c in self.calls)
