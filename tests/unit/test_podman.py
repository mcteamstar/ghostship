"""Unit tests for transport/podman.py — PodmanClient and FakePodmanClient (TRN-284).

Covers:
- container_create: success (201) and error (500) paths
- container_exec_stdin: success and non-zero exit code
- container_archive_put / container_archive_get: success
- network_create / network_connect / network_disconnect: success
- volume_create / volume_remove: success
- Socket failure (connection refused) raises structured exception
- FakePodmanClient interface parity: every public method on PodmanClient exists
  on FakePodmanClient with a compatible signature
"""

from __future__ import annotations

import inspect
import types
import unittest
from unittest.mock import MagicMock, patch


# ── Minimal httpx stub helpers ────────────────────────────────────────────────

def _httpx():
    """Return the stub httpx2/httpx module installed by conftest."""
    import sys
    return sys.modules.get("httpx2") or sys.modules.get("httpx")


class _FakeResponse:
    """Minimal HTTP response stub."""

    def __init__(self, status_code: int, content: bytes = b"", json_data=None):
        self.status_code = status_code
        self.content = content
        self._json_data = json_data
        self.headers = {}

    def json(self):
        if self._json_data is not None:
            return self._json_data
        import json
        return json.loads(self.content) if self.content else {}

    def raise_for_status(self):
        httpx = _httpx()
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=None,
                response=self,
            )

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    def iter_bytes(self, chunk_size=65536):
        offset = 0
        while offset < len(self.content):
            yield self.content[offset:offset + chunk_size]
            offset += chunk_size

    def close(self):
        pass

    def read(self):
        return self.content


# ── Task 1.1: respx not available — confirmed in conftest setup ───────────────
# respx is absent; tests use unittest.mock to patch httpx.Client.send / request.


# ── TestContainerCreate ───────────────────────────────────────────────────────

class TestContainerCreate(unittest.TestCase):
    """container_create: success (201/200) and error (500) paths."""

    def _make_client(self, mock_client):
        """Build a PodmanClient using mock_client as the inner HTTP client."""
        try:
            from podman import PodmanClient  # container flat /app/
        except ModuleNotFoundError:
            from transport.podman import PodmanClient  # local dev
        pc = PodmanClient.__new__(PodmanClient)
        pc._sock_path = "/fake.sock"
        pc._c = mock_client
        return pc

    def test_container_create_success(self):
        """Successful create returns a dict with the container Id."""
        mock_client = MagicMock()
        mock_resp = _FakeResponse(201, b'{"Id": "abc123"}', {"Id": "abc123"})
        mock_client.request.return_value = mock_resp
        pc = self._make_client(mock_client)
        result = pc.container_create(
            name="gs-test",
            image="localhost/kirocrew:latest",
            env={"KEY": "val"},
            network="ghost-network",
            workspace_volume="gs-vol-test",
            home_volume="gs-home-test",
        )
        self.assertEqual(result.get("Id"), "abc123")
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args
        self.assertEqual(call_kwargs[0][0], "POST")

    def test_container_create_error_raises(self):
        """A 500 response from container_create raises HTTPStatusError."""
        httpx = _httpx()
        mock_client = MagicMock()
        err_resp = _FakeResponse(500, b"internal error")
        mock_client.request.return_value = err_resp
        pc = self._make_client(mock_client)
        with self.assertRaises(httpx.HTTPStatusError):
            pc.container_create(
                name="gs-bad",
                image="bad-image",
                env={},
                network="net",
                workspace_volume="vol",
                home_volume="hvol",
            )


# ── TestContainerExecStdin ────────────────────────────────────────────────────

class TestContainerExecStdin(unittest.TestCase):
    """container_exec_stdin: success and non-zero exit code raise RuntimeError."""

    def _make_client_with_socket(self, sock_path="/fake.sock"):
        """Build a PodmanClient stub where the socket interaction is mocked."""
        try:
            from podman import PodmanClient  # container flat /app/
        except ModuleNotFoundError:
            from transport.podman import PodmanClient  # local dev
        pc = PodmanClient.__new__(PodmanClient)
        pc._sock_path = sock_path
        pc._c = MagicMock()
        return pc

    def test_exec_stdin_success(self):
        """exec_stdin: returns stdout when exit code is 0."""
        pc = self._make_client_with_socket()

        # Stub _req (POST .../exec) → returns exec id
        pc._req = MagicMock(return_value={"Id": "exec-001"})

        # Build a fake socket that produces 101 upgrade headers + payload, then EOF.
        header = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: tcp\r\n\r\n"
        # Multiplexed stdout frame: type=1, reserved 3 bytes, 4-byte big-endian size=5, data=b"hello"
        import struct
        frame = b"\x01\x00\x00\x00" + struct.pack(">I", 5) + b"hello"

        # Provide both the 101 header chunk (with empty remainder) and a frame chunk, then EOF
        call_count = [0]

        def fake_recv(size):
            call_count[0] += 1
            if call_count[0] == 1:
                return header
            elif call_count[0] == 2:
                return frame
            else:
                return b""  # EOF

        fake_sock = MagicMock()
        fake_sock.recv = MagicMock(side_effect=fake_recv)
        fake_sock.sendall = MagicMock()
        fake_sock.connect = MagicMock()
        fake_sock.shutdown = MagicMock()
        fake_sock.close = MagicMock()
        fake_sock.__enter__ = MagicMock(return_value=fake_sock)
        fake_sock.__exit__ = MagicMock(return_value=False)

        # Stub exec inspect: ExitCode=0
        inspect_resp = _FakeResponse(200, b'{"ExitCode": 0}', {"ExitCode": 0})
        pc._c.get.return_value = inspect_resp

        with patch("socket.socket", return_value=fake_sock):
            result = pc.container_exec_stdin(
                container="gs-test",
                cmd=["cat"],
                stdin_data=b"data",
            )
        self.assertIn("hello", result)

    def test_exec_stdin_nonzero_exit_raises(self):
        """exec_stdin: non-zero exit code raises RuntimeError."""
        pc = self._make_client_with_socket()
        pc._req = MagicMock(return_value={"Id": "exec-002"})

        header = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: tcp\r\n\r\n"

        call_count = [0]

        def fake_recv(size):
            call_count[0] += 1
            if call_count[0] == 1:
                return header
            else:
                return b""  # EOF immediately after headers

        fake_sock = MagicMock()
        fake_sock.recv = MagicMock(side_effect=fake_recv)
        fake_sock.sendall = MagicMock()
        fake_sock.connect = MagicMock()
        fake_sock.shutdown = MagicMock()
        fake_sock.close = MagicMock()

        inspect_resp = _FakeResponse(200, b'{"ExitCode": 1}', {"ExitCode": 1})
        pc._c.get.return_value = inspect_resp

        with patch("socket.socket", return_value=fake_sock):
            with self.assertRaises(RuntimeError) as ctx:
                pc.container_exec_stdin(
                    container="gs-test",
                    cmd=["false"],
                    stdin_data=b"",
                )
        self.assertIn("1", str(ctx.exception))


# ── TestContainerArchive ──────────────────────────────────────────────────────

class TestContainerArchive(unittest.TestCase):
    """container_archive_put and container_archive_get: success paths."""

    def _make_client(self):
        try:
            from podman import PodmanClient
        except ModuleNotFoundError:
            from transport.podman import PodmanClient
        pc = PodmanClient.__new__(PodmanClient)
        pc._sock_path = "/fake.sock"
        pc._c = MagicMock()
        return pc

    def test_archive_put_success(self):
        """archive_put: 200 OK should not raise."""
        pc = self._make_client()
        put_resp = _FakeResponse(200, b"")
        put_resp.close = MagicMock()
        pc._c.request.return_value = put_resp
        # Should not raise
        pc.container_archive_put("gs-test", "/workspace", b"\x00tar\x00")
        pc._c.request.assert_called_once()

    def test_archive_get_success(self):
        """archive_get: 200 returns a streaming response."""
        pc = self._make_client()
        get_resp = _FakeResponse(200, b"\x00tar\x00")
        get_resp.stream = True

        # build_request returns a dummy; send returns get_resp
        pc._c.build_request = MagicMock(return_value=MagicMock())
        pc._c.send = MagicMock(return_value=get_resp)

        result = pc.container_archive_get("gs-test", "/workspace/file.txt")
        self.assertEqual(result.status_code, 200)

    def test_archive_get_error_raises(self):
        """archive_get: non-200 raises RuntimeError."""
        pc = self._make_client()
        err_resp = _FakeResponse(404, b"not found")
        err_resp.read = MagicMock(return_value=b"not found")

        pc._c.build_request = MagicMock(return_value=MagicMock())
        pc._c.send = MagicMock(return_value=err_resp)

        with self.assertRaises(RuntimeError):
            pc.container_archive_get("gs-test", "/missing")


# ── TestNetworkOps ────────────────────────────────────────────────────────────

class TestNetworkOps(unittest.TestCase):
    """network_create, network_connect, network_disconnect: success paths."""

    def _make_client(self):
        try:
            from podman import PodmanClient
        except ModuleNotFoundError:
            from transport.podman import PodmanClient
        pc = PodmanClient.__new__(PodmanClient)
        pc._sock_path = "/fake.sock"
        pc._c = MagicMock()
        return pc

    def test_network_create_success(self):
        """network_create: 201 does not raise."""
        pc = self._make_client()
        pc._req = MagicMock(return_value={})
        pc.network_create("ghost-net")
        pc._req.assert_called_once()

    def test_network_create_409_idempotent(self):
        """network_create: 409 (already exists) is silently ignored."""
        pc = self._make_client()
        httpx = _httpx()
        err = httpx.HTTPStatusError("conflict", request=None, response=_FakeResponse(409))
        pc._req = MagicMock(side_effect=err)
        # Should not raise
        pc.network_create("ghost-net")

    def test_network_connect_success(self):
        """network_connect: 204 does not raise."""
        pc = self._make_client()
        pc._c.post.return_value = _FakeResponse(204, b"")
        pc.network_connect("gs-test", "ghost-net")
        pc._c.post.assert_called_once()

    def test_network_connect_409_idempotent(self):
        """network_connect: 409 (already connected) is silently ignored."""
        pc = self._make_client()
        pc._c.post.return_value = _FakeResponse(409, b"already connected")
        # Should not raise
        pc.network_connect("gs-test", "ghost-net")

    def test_network_disconnect_success(self):
        """network_disconnect: 204 does not raise."""
        pc = self._make_client()
        pc._c.post.return_value = _FakeResponse(204, b"")
        pc.network_disconnect("gs-test", "ghost-net")
        pc._c.post.assert_called_once()


# ── TestVolumeOps ─────────────────────────────────────────────────────────────

class TestVolumeOps(unittest.TestCase):
    """volume_create and volume_remove: success paths."""

    def _make_client(self):
        try:
            from podman import PodmanClient
        except ModuleNotFoundError:
            from transport.podman import PodmanClient
        pc = PodmanClient.__new__(PodmanClient)
        pc._sock_path = "/fake.sock"
        pc._c = MagicMock()
        return pc

    def test_volume_create_success(self):
        """volume_create: 201 does not raise."""
        pc = self._make_client()
        pc._req = MagicMock(return_value={})
        pc.volume_create("gs-vol-test")
        pc._req.assert_called_once()

    def test_volume_create_409_idempotent(self):
        """volume_create: 409 (already exists) is silently ignored."""
        httpx = _httpx()
        pc = self._make_client()
        err = httpx.HTTPStatusError("conflict", request=None, response=_FakeResponse(409))
        pc._req = MagicMock(side_effect=err)
        pc.volume_create("gs-vol-test")

    def test_volume_remove_success(self):
        """volume_remove: 200 does not raise."""
        pc = self._make_client()
        del_resp = _FakeResponse(200, b"")
        del_resp.raise_for_status = MagicMock()
        pc._c.delete.return_value = del_resp
        pc.volume_remove("gs-vol-test")
        pc._c.delete.assert_called_once()

    def test_volume_remove_404_idempotent(self):
        """volume_remove: 404 (already gone) is silently ignored."""
        httpx = _httpx()
        pc = self._make_client()
        err_resp = _FakeResponse(404, b"")
        err = httpx.HTTPStatusError("not found", request=None, response=err_resp)
        del_resp = MagicMock()
        del_resp.raise_for_status.side_effect = err
        pc._c.delete.return_value = del_resp
        # Should not raise
        pc.volume_remove("gs-vol-missing")


# ── TestSocketFailure ─────────────────────────────────────────────────────────

class TestSocketFailure(unittest.TestCase):
    """Socket failures (connection refused) raise a structured exception."""

    def test_socket_unavailable_raises_runtime_error(self):
        """When the Podman socket does not exist, _get_podman raises RuntimeError."""
        try:
            from podman import _get_podman  # container flat /app/
        except ModuleNotFoundError:
            from transport.podman import _get_podman  # local dev

        with patch("os.path.exists", return_value=False):
            with patch("pathlib.Path.exists", return_value=False):
                # Reset singleton
                try:
                    import podman as _pm
                except ModuleNotFoundError:
                    from transport import podman as _pm
                _pm._podman = None
                with self.assertRaises(RuntimeError) as ctx:
                    _get_podman()
                self.assertIn("socket", str(ctx.exception).lower())


# ── Task 1.3: FakePodmanClient interface parity ───────────────────────────────

class TestFakePodmanClientParity(unittest.TestCase):
    """Every abstract method of ContainerRuntime (the interface) exists on
    FakePodmanClient with a compatible signature (same positional params
    excluding 'self').

    We test parity against ContainerRuntime (the ABC) rather than PodmanClient
    directly because PodmanClient contains non-interface methods
    (e.g. container_exec_pty_stdin, worker_run helpers) that are not part of the
    contract FakePodmanClient is expected to satisfy.
    """

    def test_all_abstract_methods_present_with_compatible_signatures(self):
        try:
            from podman import ContainerRuntime  # container flat /app/
        except ModuleNotFoundError:
            from transport.podman import ContainerRuntime  # local dev
        from tests.fakes import FakePodmanClient

        # Collect only the abstractmethods from the ABC
        abc_methods = {
            name: method
            for name, method in inspect.getmembers(ContainerRuntime, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        fake_methods = {
            name: method
            for name, method in inspect.getmembers(FakePodmanClient, predicate=inspect.isfunction)
            if not name.startswith("_")
        }

        for name, real_fn in abc_methods.items():
            with self.subTest(method=name):
                self.assertIn(
                    name, fake_methods,
                    f"FakePodmanClient is missing interface method: {name}",
                )
                real_sig = inspect.signature(real_fn)
                fake_sig = inspect.signature(fake_methods[name])

                real_params = [
                    p for p in real_sig.parameters.values()
                    if p.name != "self"
                ]
                fake_params = [
                    p for p in fake_sig.parameters.values()
                    if p.name != "self"
                ]

                # Compare required positional-or-keyword params (no defaults)
                real_required = [
                    p.name for p in real_params
                    if p.default is inspect.Parameter.empty
                    and p.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]
                fake_required = [
                    p.name for p in fake_params
                    if p.default is inspect.Parameter.empty
                    and p.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ]

                self.assertEqual(
                    real_required, fake_required,
                    f"{name}: ABC required params {real_required} != fake {fake_required}",
                )


if __name__ == "__main__":
    unittest.main()
