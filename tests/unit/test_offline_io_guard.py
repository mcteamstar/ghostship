"""The shared offline fixture blocks external I/O but permits local transports."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess

import httpx2 as httpx
import pytest

from tests.conftest import OfflineNetworkAccess, OfflinePodmanAccess


def test_external_http_transport_is_blocked():
    with httpx.Client() as client:
        with pytest.raises(OfflineNetworkAccess, match="cannot use HTTPTransport"):
            client.get("http://transport.invalid/")


def test_podman_unix_socket_transport_is_blocked():
    transport = httpx.HTTPTransport(uds="/run/podman/podman.sock")
    with httpx.Client(transport=transport, base_url="http://localhost") as client:
        with pytest.raises(OfflineNetworkAccess, match="cannot use HTTPTransport"):
            client.get("/v4.0.0/libpod/info")


@pytest.mark.parametrize("command", [["podman", "info"], ["podman-compose", "ps"]])
def test_podman_process_is_blocked(command):
    with pytest.raises(OfflinePodmanAccess, match="cannot invoke Podman"):
        subprocess.run(command, check=False)


def test_raw_podman_socket_is_blocked():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        with pytest.raises(OfflinePodmanAccess, match="cannot connect to a Podman socket"):
            sock.connect("/run/user/1000/podman/podman.sock")
    finally:
        sock.close()


def test_mock_transport_is_allowed():
    def respond(request):
        return httpx.Response(200, request=request, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = client.get("http://gateway.test/health")

    assert response.json() == {"ok": True}


def test_in_process_asgi_transport_is_allowed():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://asgi.test",
        ) as client:
            return await client.get("/")

    loop = asyncio.new_event_loop()
    try:
        response = loop.run_until_complete(request())
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())

    assert response.status_code == 200
    assert response.text == "ok"


def test_persistent_data_uses_per_test_paths(tmp_path):
    import transport.credentials as credentials
    import transport.files as files
    import transport.lifecycle as lifecycle
    import transport.login as login
    import transport.registry as registry
    import transport.tools as tools

    data_dir = tmp_path / "data"
    assert registry.DATA_DIR == data_dir
    assert registry.REGISTRY_PATH == data_dir / "crews.json"
    assert files.DATA_DIR == lifecycle.DATA_DIR == data_dir
    assert files._FILE_SECRET == os.environ["GA_FILE_SECRET"]
    for store in (credentials.store, lifecycle._cred_store, login._cred_store, tools._cred_store):
        assert store._dir == data_dir / "credentials"
    assert registry._crew_secret_path("crew-a").parent == data_dir / "secrets"
