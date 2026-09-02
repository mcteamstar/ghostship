"""Podman client — PodmanClient class, ContainerRuntime ABC, HTTP clients,
memory helpers, and the _podman singleton.

The shared HTTP clients (_http, _async_http) live here because they are owned
by this module. Proxy handlers in server.py import them from here.
"""

from __future__ import annotations

import json
import logging
import secrets
import socket
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config

cfg = Config.from_env()

PODMAN_SOCK = cfg.podman_socket
KIRO_WORKSPACE_ROOT = "/home/kirocrew/workplace/kirocrew-workspace"

# Worker sidecar (TRN-81) — the transport's disposable utility container for
# reading files/bundles/diffs from STOPPED crew volumes without waking the
# crew. Built by install.sh from crews/_worker/. The crew workspace volume is
# mounted read-only at WORKER_MOUNT; worker commands operate under that path.
WORKER_IMAGE = "localhost/gs-worker:latest"
WORKER_MOUNT = "/workspace"
CREW_VOLUME_PREFIX = "gs-vol-"

logger = logging.getLogger(__name__)


class WorkerImageMissing(RuntimeError):
    """Raised when the worker image (localhost/gs-worker:latest) is not present."""


class WorkerCommandError(RuntimeError):
    """Raised when a worker command exits non-zero.

    Carries the exit code and captured output so callers can map it to the
    right HTTP status (e.g. a `cat` non-zero → 404 file-not-found, a git
    failure → 500 with git stderr).
    """

    def __init__(self, exit_code: int, output: str) -> None:
        self.exit_code = exit_code
        self.output = output
        super().__init__(
            f"worker command exited {exit_code}: {output.strip() or '(no output)'}"
        )

# ── Shared HTTP clients ───────────────────────────────────────────────────────

_http = httpx.Client(timeout=60.0)
# Async client used exclusively by the proxy handlers. The synchronous _http
# client is reserved for MCP tool functions that run in Starlette's threadpool
# executor. Using an async client here avoids blocking the event loop while
# streaming potentially large proxy response bodies.
_async_http = httpx.AsyncClient(timeout=60.0)


# ── ContainerRuntime ABC ─────────────────────────────────────────────────────

class ContainerRuntime(ABC):
    """Minimal interface that PodmanClient satisfies."""

    @abstractmethod
    def container_create(
        self,
        name: str,
        image: str,
        env: dict,
        network: str,
        workspace_volume: str,
        home_volume: str,

    ) -> dict: ...

    @abstractmethod
    def container_start(self, name: str) -> None: ...

    @abstractmethod
    def container_stop(self, name: str) -> None: ...

    @abstractmethod
    def container_remove(self, name: str) -> None: ...

    @abstractmethod
    def container_inspect(self, name: str) -> dict: ...

    @abstractmethod
    def container_exists(self, name: str) -> bool: ...

    @abstractmethod
    def container_is_running(self, name: str) -> bool: ...

    @abstractmethod
    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str: ...

    @abstractmethod
    def container_exec_checked(
        self, name: str, cmd: list[str], env: dict | None = None
    ) -> str: ...

    @abstractmethod
    def container_exec_stdin(
        self, container: str, cmd: list[str], stdin_data: bytes
    ) -> str:
        """Run a one-shot exec, write stdin_data to the process's stdin, wait for exit,
        and return stdout as a string."""
        ...

    @abstractmethod
    def container_archive_put(
        self, name: str, workspace_path: str, tar_body: bytes
    ) -> None: ...

    @abstractmethod
    def container_archive_get(self, name: str, workspace_path: str) -> httpx.Response: ...

    @abstractmethod
    def volume_create(self, name: str) -> None: ...

    @abstractmethod
    def volume_remove(self, name: str) -> None: ...

    @abstractmethod
    def worker_run(
        self, volume_name: str, cmd: list[str], timeout: float = 60.0
    ) -> bytes: ...

    @abstractmethod
    def volume_name_for_crew(self, crew_id: str) -> str: ...

    @abstractmethod
    def network_create(self, name: str) -> None: ...

    @abstractmethod
    def system_info(self) -> dict: ...


# ── Podman client ─────────────────────────────────────────────────────────────

class PodmanClient(ContainerRuntime):
    """Minimal Podman REST client via Unix socket."""

    def __init__(self, sock_path: str) -> None:
        self._sock_path = sock_path
        transport = httpx.HTTPTransport(uds=sock_path)
        self._c = httpx.Client(
            transport=transport,
            base_url="http://d/v4.0.0",
            timeout=120.0,
        )

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self._c.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else {}

    # ── containers ────────────────────────────────────────────────────────────

    def container_create(
        self,
        name: str,
        image: str,
        env: dict,
        network: str,
        workspace_volume: str,
        home_volume: str,

    ) -> dict:
        spec: dict[str, Any] = {
            "name": name,
            "image": image,
            "env": env,
            "netns": {"nsmode": "bridge"},
            "Networks": {network: {}},
            "volumes": [
                {"name": workspace_volume,
                 "dest": KIRO_WORKSPACE_ROOT},
                {"name": home_volume, "dest": "/home/kirocrew"},
            ],
            # TRN-93: prevent privilege escalation via setuid binaries and drop
            # the two highest-risk capabilities for crew containers.
            "no_new_privileges": True,
            "cap_drop": ["CAP_NET_RAW", "CAP_SYS_ADMIN"],
        }
        return self._req("POST", "/libpod/containers/create", json=spec)

    def container_start(self, name: str) -> None:
        r = self._c.post(f"/libpod/containers/{name}/start")
        if r.status_code not in (200, 204):
            r.raise_for_status()

    def container_stop(self, name: str) -> None:
        try:
            self._c.post(
                f"/libpod/containers/{name}/stop", params={"t": 10}
            ).raise_for_status()
        except Exception:
            pass

    def container_remove(self, name: str) -> None:
        try:
            self._c.delete(
                f"/libpod/containers/{name}", params={"force": "true"}
            ).raise_for_status()
        except Exception:
            pass

    def container_inspect(self, name: str) -> dict:
        """Inspect a container, returning the full JSON object."""
        r = self._c.get(f"/libpod/containers/{name}/json")
        r.raise_for_status()
        return r.json()

    def container_exists(self, name: str) -> bool:
        return self._c.get(f"/libpod/containers/{name}/json").status_code == 200

    def container_is_running(self, name: str) -> bool:
        r = self._c.get(f"/libpod/containers/{name}/json")
        if r.status_code != 200:
            return False
        return r.json().get("State", {}).get("Status") == "running"

    def system_info(self) -> dict:
        """Query Podman system info (GET /libpod/info)."""
        return self._req("GET", "/libpod/info")

    def _demux(self, raw: bytes) -> str:
        """Demux Docker multiplexed stream format into plain text."""
        output = []
        i = 0
        while i + 8 <= len(raw):
            stream_type = raw[i]
            size = int.from_bytes(raw[i + 4:i + 8], "big")
            i += 8
            chunk = raw[i:i + size].decode("utf-8", errors="replace")
            if stream_type in (1, 2):
                output.append(chunk)
            i += size
        if not output and raw:
            return raw.decode("utf-8", errors="replace")
        return "".join(output)

    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        """Run a command in a container, return combined stdout+stderr."""
        spec: dict = {
            "AttachStdout": True, "AttachStderr": True, "Cmd": cmd,
        }
        if env:
            spec["Env"] = [f"{k}={v}" for k, v in env.items()]
        r = self._req("POST", f"/libpod/containers/{name}/exec", json=spec)
        exec_id = r["Id"]
        resp = self._c.post(
            f"/libpod/exec/{exec_id}/start",
            json={"Detach": False},
            headers={"Content-Type": "application/json"},
        )
        return self._demux(resp.content)

    def container_exec_pty_stdin(
        self, name: str, cmd: list[str]
    ) -> tuple[str, "socket.socket"]:
        """Start a PTY+stdin exec session via a raw Unix socket.

        Returns (exec_id, raw_socket). The socket is bidirectional: read from
        it to get PTY output, write to it to send stdin. The caller is
        responsible for closing the socket when done.

        kiro-cli ignores --identity-provider / --region flags when running
        interactively (upstream bug). This method provides a writable stdin so
        the caller can answer the interactive prompts programmatically.
        """
        spec: dict = {
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": True,
            "Cmd": cmd,
        }
        r = self._req("POST", f"/libpod/containers/{name}/exec", json=spec)
        exec_id = r["Id"]

        # Open a raw Unix socket — httpx can't do bidirectional hijacking.
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._sock_path)

        body = json.dumps({"Detach": False}).encode()
        request_line = f"POST /v4.0.0/libpod/exec/{exec_id}/start HTTP/1.1\r\n"
        headers = (
            "Host: d\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: tcp\r\n"
            "\r\n"
        )
        sock.sendall((request_line + headers).encode() + body)

        # Read until end of HTTP response headers (the 101 Switching Protocols).
        response_buf = bytearray()
        while b"\r\n\r\n" not in response_buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Socket closed before exec upgrade completed")
            response_buf.extend(chunk)

        return exec_id, sock

    @staticmethod
    def _check_response(response: Any, operation: str) -> None:
        if 200 <= response.status_code < 300:
            return
        try:
            detail = response.text.strip()
        except Exception:
            detail = ""
        if not detail:
            raw = getattr(response, "content", b"")
            if isinstance(raw, bytes):
                detail = raw.decode("utf-8", errors="replace").strip()
            else:
                detail = str(raw).strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(
            f"{operation} failed with HTTP {response.status_code}{suffix}"
        )

    def container_archive_put(
        self,
        name: str,
        workspace_path: str,
        tar_body: bytes,
    ) -> None:
        """Copy a generated tar stream into a container workspace."""
        response = self._c.request(
            "PUT",
            f"/libpod/containers/{name}/archive",
            params={"path": workspace_path, "pause": "false"},
            content=tar_body,
            headers={"Content-Type": "application/x-tar"},
        )
        try:
            self._check_response(response, "Podman archive PUT")
        finally:
            response.close()

    def container_archive_get(
        self,
        name: str,
        workspace_path: str,
    ) -> httpx.Response:
        """Open a raw tar response for a file in a container workspace."""
        request = self._c.build_request(
            "GET",
            f"/libpod/containers/{name}/archive",
            params={"path": workspace_path},
        )
        response = self._c.send(request, stream=True)
        if 200 <= response.status_code < 300:
            return response

        try:
            raw = response.read()
        except Exception:
            raw = b""
        try:
            response.close()
        finally:
            detail = raw.decode("utf-8", errors="replace").strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(
            f"Podman archive GET failed with HTTP {response.status_code}{suffix}"
        )

    def container_exec_stdin(
        self,
        container: str,
        cmd: list[str],
        stdin_data: bytes,
    ) -> str:
        """Run a one-shot exec, write stdin_data to the process's stdin, wait for exit,
        and return stdout as a string.  Raises RuntimeError if the process exits non-zero.

        Uses the Podman exec API with AttachStdin=True, then hijacks the connection
        via a raw Unix socket to write stdin_data before closing the write side.
        The response is demuxed using the existing _demux helper.  After the socket
        closes, the exec is inspected (GET /libpod/exec/{id}/json) to retrieve the
        exit code — identical to the pattern used by container_exec_checked.
        """
        spec: dict = {
            "AttachStdin": True,
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": False,
            "Cmd": cmd,
        }
        r = self._req("POST", f"/libpod/containers/{container}/exec", json=spec)
        exec_id = r["Id"]

        # Open a raw Unix socket for hijacked stdin/stdout communication.
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(self._sock_path)

        body = json.dumps({"Detach": False}).encode()
        request_line = f"POST /v4.0.0/libpod/exec/{exec_id}/start HTTP/1.1\r\n"
        headers = (
            "Host: d\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: tcp\r\n"
            "\r\n"
        )
        sock.sendall((request_line + headers).encode() + body)

        # Read until end of HTTP response headers (the 101 Switching Protocols).
        response_buf = bytearray()
        while b"\r\n\r\n" not in response_buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("Socket closed before exec upgrade completed")
            response_buf.extend(chunk)

        # Write stdin_data then shut down the write side so the process sees EOF.
        try:
            sock.sendall(stdin_data)
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass

        # Read all remaining output from the process.
        output_buf = bytearray()
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                output_buf.extend(chunk)
        finally:
            sock.close()

        output = self._demux(bytes(output_buf))

        # Inspect the exec to get the exit code — same pattern as container_exec_checked.
        inspected = self._c.get(f"/libpod/exec/{exec_id}/json")
        try:
            self._check_response(inspected, "Podman exec inspect")
            exit_code = inspected.json().get("ExitCode")
        finally:
            inspected.close()

        if exit_code is None:
            raise RuntimeError(
                f"Podman exec {exec_id} returned no exit code: {output.strip()}"
            )
        if exit_code != 0:
            detail = output.strip() or "(no output)"
            raise RuntimeError(
                f"Podman exec {exec_id} exited with code {exit_code}: {detail}"
            )
        return output

    def container_exec_checked(
        self,
        name: str,
        cmd: list[str],
        env: dict | None = None,
    ) -> str:
        """Run a no-stdin command and fail when its process exits non-zero."""
        spec: dict = {
            "AttachStdout": True,
            "AttachStderr": True,
            "Cmd": cmd,
        }
        if env:
            spec["Env"] = [f"{k}={v}" for k, v in env.items()]

        created = self._req(
            "POST", f"/libpod/containers/{name}/exec", json=spec
        )
        exec_id = created["Id"]
        started = self._c.post(
            f"/libpod/exec/{exec_id}/start",
            json={"Detach": False},
            headers={"Content-Type": "application/json"},
        )
        try:
            self._check_response(started, "Podman exec start")
            output = self._demux(started.content)
        finally:
            started.close()

        inspected = self._c.get(f"/libpod/exec/{exec_id}/json")
        try:
            self._check_response(inspected, "Podman exec inspect")
            exit_code = inspected.json().get("ExitCode")
        finally:
            inspected.close()

        if exit_code is None:
            raise RuntimeError(
                f"Podman exec {exec_id} returned no exit code: {output.strip()}"
            )
        if exit_code != 0:
            detail = output.strip() or "(no output)"
            raise RuntimeError(
                f"Podman exec {exec_id} exited with code {exit_code}: {detail}"
            )
        return output

    # ── volumes ───────────────────────────────────────────────────────────────

    def volume_create(self, name: str) -> None:
        try:
            self._req("POST", "/libpod/volumes/create", json={"Name": name})
        except Exception:
            pass  # already exists

    def volume_remove(self, name: str) -> None:
        try:
            self._c.delete(
                f"/libpod/volumes/{name}", params={"force": "true"}
            ).raise_for_status()
        except Exception:
            pass

    # ── worker sidecar (TRN-81) ─────────────────────────────────────────────

    @staticmethod
    def volume_name_for_crew(crew_id: str) -> str:
        """Return the workspace volume name for a crew (``gs-vol-{crew_id}``)."""
        return f"{CREW_VOLUME_PREFIX}{crew_id}"

    def _image_exists(self, image: str) -> bool:
        r = self._c.get(f"/libpod/images/{image}/exists")
        return r.status_code == 204

    def worker_run(
        self, volume_name: str, cmd: list[str], timeout: float = 60.0
    ) -> bytes:
        """Run one command in a disposable worker container and return stdout.

        Spins up ``localhost/gs-worker:latest`` with ``volume_name`` mounted
        read-only at ``/workspace``, runs ``cmd``, waits for exit, and always
        removes the container. Equivalent to::

            podman run --rm -v {volume_name}:/workspace:ro \
                localhost/gs-worker:latest {cmd}

        Returns the raw stdout bytes on success. Raises:
          * ``WorkerImageMissing`` if the worker image is not present;
          * ``WorkerCommandError`` (with exit code + combined output) if the
            command exits non-zero;
          * ``RuntimeError`` for any other Podman/infra failure.

        The container mounts the volume ``:ro`` and joins no network. Because
        it is short-lived and read-only, concurrent workers on the same volume
        are safe and need no coordination.
        """
        if not self._image_exists(WORKER_IMAGE):
            raise WorkerImageMissing(
                f"Worker image {WORKER_IMAGE} is not present. "
                "Run install.sh to build it."
            )

        name = f"gs-worker-{secrets.token_hex(8)}"
        spec = {
            "name": name,
            "image": WORKER_IMAGE,
            "command": cmd,
            "remove": True,  # auto-remove on exit (--rm)
            "netns": {"nsmode": "none"},
            "volumes": [
                {
                    "name": volume_name,
                    "dest": WORKER_MOUNT,
                    "options": ["ro"],
                },
            ],
            # TRN-93: prevent privilege escalation and drop high-risk capabilities.
            "no_new_privileges": True,
            "cap_drop": ["CAP_NET_RAW", "CAP_SYS_ADMIN"],
        }

        created = False
        try:
            self._req("POST", "/libpod/containers/create", json=spec)
            created = True
            self.container_start(name)

            # Block until the container exits, capturing its exit code.
            wait = self._c.post(
                f"/libpod/containers/{name}/wait",
                params={"condition": "exited"},
                timeout=timeout,
            )
            wait.raise_for_status()
            try:
                exit_code = int(wait.json())
            except (ValueError, TypeError):
                # Podman may return {"StatusCode": N, "Error": {...}} instead of
                # a bare integer (older API versions / edge cases). Guard against
                # None or other non-dict responses so .get() doesn't AttributeError.
                body = wait.json() if wait.content else None
                if isinstance(body, dict):
                    exit_code = int(body.get("StatusCode", 1))
                else:
                    exit_code = 1

            # Fetch stdout+stderr from the logs endpoint (demuxed).
            logs = self._c.get(
                f"/libpod/containers/{name}/logs",
                params={"stdout": "true", "stderr": "true"},
            )
            raw = logs.content if logs.status_code == 200 else b""
            output = self._demux(raw)

            if exit_code != 0:
                raise WorkerCommandError(exit_code, output)
            # stdout only: re-demux keeping just stream type 1 would drop stderr,
            # but for the success path callers want the command's stdout bytes.
            return self._demux_stdout(raw)
        except (WorkerCommandError, WorkerImageMissing):
            raise
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Worker container failed: {e}") from e
        finally:
            # remove:true handles the happy path; force-remove covers a worker
            # that failed to start or was interrupted before auto-removal.
            if created:
                try:
                    self._c.delete(
                        f"/libpod/containers/{name}", params={"force": "true"}
                    )
                except Exception:
                    pass

    def _demux_stdout(self, raw: bytes) -> bytes:
        """Demux a Docker multiplexed stream, keeping only stdout (type 1) bytes.

        Unlike ``_demux`` (which returns combined stdout+stderr as text), this
        returns raw stdout bytes so binary payloads (git bundles) survive.
        """
        out = bytearray()
        i = 0
        matched = False
        while i + 8 <= len(raw):
            stream_type = raw[i]
            size = int.from_bytes(raw[i + 4:i + 8], "big")
            i += 8
            chunk = raw[i:i + size]
            if stream_type == 1:
                out.extend(chunk)
                matched = True
            i += size
        if not matched and raw:
            # Stream was not multiplexed (no TTY framing) — return as-is.
            return raw
        return bytes(out)

    # ── networks ──────────────────────────────────────────────────────────────

    def network_create(self, name: str) -> None:
        try:
            self._req("POST", "/libpod/networks/create",
                      json={"name": name, "dns_enabled": True})
        except Exception:
            pass  # already exists


# ── Singleton ─────────────────────────────────────────────────────────────────

_podman: PodmanClient | None = None


def _get_podman() -> PodmanClient:
    global _podman
    if _podman is None:
        if not Path(PODMAN_SOCK).exists():
            raise RuntimeError(
                f"Podman socket not found at {PODMAN_SOCK}. "
                "Mount: -v /run/user/1000/podman/podman.sock:"
                "/run/user/1000/podman/podman.sock"
            )
        _podman = PodmanClient(PODMAN_SOCK)
    return _podman


# ── Memory helpers ────────────────────────────────────────────────────────────

def _get_host_memory_gb(podman: PodmanClient) -> float:
    """Extract available memory (GB) from Podman system info.

    Prefers memAvailable (accounts for reclaimable page cache / buffers) over
    memFree (raw uncommitted pages only).  Falls back to memFree when the
    kernel or Podman build does not expose memAvailable.
    """
    info = podman.system_info()
    host = info.get("host", {})
    mem_bytes = host.get("memAvailable", host.get("memFree", 0))
    return round(mem_bytes / (1024 ** 3), 1)


_host_memory_cache: tuple[float, float] | None = None
_host_memory_cache_lock = threading.Lock()


def _get_host_memory_gb_cached(podman: PodmanClient) -> float | None:
    """Return available memory with 5-second TTL cache.

    Returns None if Podman info fails. Thread-safe via _host_memory_cache_lock.
    """
    global _host_memory_cache
    now = time.monotonic()
    with _host_memory_cache_lock:
        if _host_memory_cache is not None:
            ts, value = _host_memory_cache
            if now - ts < 5.0:
                return value
    try:
        value = _get_host_memory_gb(podman)
        with _host_memory_cache_lock:
            _host_memory_cache = (now, value)
        return value
    except Exception:
        return None


def _wait_for_memory(podman: PodmanClient, required_gb: float, timeout_secs: int) -> float:
    """Block until host has required_gb free, or timeout_secs expires.

    Returns current free GB (may be < required_gb on timeout).
    """
    deadline = time.monotonic() + timeout_secs
    while True:
        free_gb = _get_host_memory_gb(podman)
        if free_gb >= required_gb:
            return free_gb
        if time.monotonic() >= deadline:
            return free_gb
        time.sleep(5)
