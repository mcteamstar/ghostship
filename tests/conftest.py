"""Shared test isolation for unit tests and offline Python integrations."""

from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# transport.files loads its signing key during import. Keep every pytest process
# away from a developer's /data key, including mixed unit/integration runs.
os.environ["GA_FILE_SECRET"] = "test-file-secret-value-32chars!!"


class OfflineNetworkAccess(RuntimeError):
    """Raised when an offline pytest suite tries to use a network transport."""


class OfflinePodmanAccess(RuntimeError):
    """Raised when an offline pytest suite tries to invoke Podman."""


_OFFLINE_INTEGRATION_FILES = {
    "test_crew_gateway_client.py",
    "test_on_demand_recovery.py",
    "test_profile_launch_flow.py",
}


def _command_name(command: Any) -> str | None:
    if isinstance(command, (str, bytes, os.PathLike)):
        try:
            parts = shlex.split(os.fsdecode(command))
        except ValueError:
            return None
    else:
        try:
            parts = list(command)
        except TypeError:
            return None
    if not parts:
        return None
    return Path(os.fsdecode(parts[0])).name


@pytest.fixture(autouse=True)
def _isolate_offline_test_boundaries(request, tmp_path, monkeypatch):
    """Use real libraries with per-test persistence and hermetic I/O guards.

    The live E2E and real-Podman integration suites intentionally reach their
    configured services. The fixture applies only to unit tests and the three
    offline Python integration suites.
    """
    test_path = Path(str(request.node.path))
    is_unit_test = "unit" in test_path.parts and "tests" in test_path.parts
    is_offline_integration = (
        "integration" in test_path.parts
        and "tests" in test_path.parts
        and test_path.name in _OFFLINE_INTEGRATION_FILES
    )
    if not (is_unit_test or is_offline_integration):
        yield
        return

    import httpx2

    def block_http(*_args, **_kwargs):
        raise OfflineNetworkAccess("offline pytest suites cannot use HTTPTransport")

    client_libraries = [httpx2]
    try:
        import httpx
    except ImportError:
        pass
    else:
        client_libraries.append(httpx)
    for client_library in set(client_libraries):
        monkeypatch.setattr(client_library.HTTPTransport, "handle_request", block_http)
        monkeypatch.setattr(client_library.AsyncHTTPTransport, "handle_async_request", block_http)

    real_popen_init = subprocess.Popen.__init__

    def guard_podman_popen_init(self, command, *args, **kwargs):
        if _command_name(command) in {"podman", "podman-compose"}:
            raise OfflinePodmanAccess("offline pytest suites cannot invoke Podman")
        return real_popen_init(self, command, *args, **kwargs)

    # Patch the constructor while keeping subprocess.Popen itself a class;
    # libraries use it in runtime type annotations during imports.
    monkeypatch.setattr(subprocess.Popen, "__init__", guard_podman_popen_init)

    real_socket_connect = socket.socket.connect

    def guard_podman_socket_connect(self, address):
        if self.family == socket.AF_UNIX and isinstance(address, (str, bytes, os.PathLike)):
            socket_path = os.fsdecode(address)
            if "podman" in socket_path.lower() and socket_path.lower().endswith(".sock"):
                raise OfflinePodmanAccess("offline pytest suites cannot connect to a Podman socket")
        return real_socket_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guard_podman_socket_connect)

    import transport.registry as registry
    import transport.credentials as credentials

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    registry_path = data_dir / "crews.json"
    monkeypatch.setattr(registry, "DATA_DIR", data_dir)
    monkeypatch.setattr(registry, "REGISTRY_PATH", registry_path)
    monkeypatch.setattr(registry.registry, "_path", registry_path)

    # Modules are imported during collection. Repoint every loaded transport
    # singleton that owns a data path or credential store before a test runs.
    real_credential_init = credentials.CredentialStore.__init__

    def credential_init_in_test_data(self, configured_data_dir=Path("/data")):
        if Path(configured_data_dir) == Path("/data"):
            configured_data_dir = data_dir
        real_credential_init(self, configured_data_dir)

    monkeypatch.setattr(credentials.CredentialStore, "__init__", credential_init_in_test_data)

    real_registry_init = registry.CrewRegistry.__init__

    def registry_init_in_test_data(self, path):
        if Path(path) == Path("/data/crews.json"):
            path = registry_path
        real_registry_init(self, path)

    monkeypatch.setattr(registry.CrewRegistry, "__init__", registry_init_in_test_data)

    # Import path-owning modules only after the temporary defaults are active;
    # this also covers a test that first imports one of them from its body.
    import transport.files
    import transport.lifecycle
    import transport.login
    import transport.tools

    for module_name, module in tuple(sys.modules.items()):
        if module is None or not module_name.startswith("transport"):
            continue
        for attr in ("DATA_DIR",):
            if getattr(module, attr, None) == Path("/data"):
                monkeypatch.setattr(module, attr, data_dir)
        for attr in ("REGISTRY_PATH", "_CREW_REGISTRY_PATH"):
            if getattr(module, attr, None) == Path("/data/crews.json"):
                monkeypatch.setattr(module, attr, registry_path)
        for attr in ("store", "_cred_store"):
            if hasattr(module, attr):
                monkeypatch.setattr(module, attr, credentials.CredentialStore(data_dir))

    yield
