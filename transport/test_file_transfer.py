from __future__ import annotations

import base64
import hashlib
import importlib
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any


def _install_import_stubs() -> None:
    """Make the stdlib tests importable in a dependency-free checkout."""
    httpx = types.ModuleType("httpx")

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class HTTPTransport:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    httpx.Client = Client  # type: ignore[attr-defined]
    httpx.HTTPTransport = HTTPTransport  # type: ignore[attr-defined]
    sys.modules["httpx"] = httpx

    mcp = types.ModuleType("mcp")
    mcp_server = types.ModuleType("mcp.server")
    mcp_mcpserver = types.ModuleType("mcp.server.mcpserver")
    mcp_server_impl = types.ModuleType("mcp.server.mcpserver.server")

    class MCPServer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def _decorator(self, *args: Any, **kwargs: Any):
            return lambda function: function

        def tool(self, *args: Any, **kwargs: Any):
            return self._decorator(*args, **kwargs)

        def resource(self, *args: Any, **kwargs: Any):
            return self._decorator(*args, **kwargs)

        def streamable_http_app(self, *args: Any, **kwargs: Any):
            """Stub: return a no-op ASGI app."""
            async def _noop(scope, receive, send):
                pass
            return _noop

    mcp_server_impl.MCPServer = MCPServer  # type: ignore[attr-defined]
    sys.modules.update({
        "mcp": mcp,
        "mcp.server": mcp_server,
        "mcp.server.mcpserver": mcp_mcpserver,
        "mcp.server.mcpserver.server": mcp_server_impl,
    })

    starlette = types.ModuleType("starlette")
    starlette_applications = types.ModuleType("starlette.applications")
    starlette_requests = types.ModuleType("starlette.requests")
    starlette_responses = types.ModuleType("starlette.responses")
    starlette_routing = types.ModuleType("starlette.routing")

    class Response:
        def __init__(self, content: Any = b"", status_code: int = 200, **kwargs: Any) -> None:
            if isinstance(content, str):
                self.body = content.encode("utf-8")
            elif isinstance(content, (dict, list)):
                import json as _json
                self.body = _json.dumps(content).encode("utf-8")
            else:
                self.body = content
            self.status_code = status_code
            self.kwargs = kwargs

    class Request:
        pass

    class Starlette:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Route:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    starlette_applications.Starlette = Starlette  # type: ignore[attr-defined]
    starlette_requests.Request = Request  # type: ignore[attr-defined]
    starlette_responses.Response = Response  # type: ignore[attr-defined]
    starlette_responses.StreamingResponse = Response  # type: ignore[attr-defined]
    starlette_responses.PlainTextResponse = Response  # type: ignore[attr-defined]
    starlette_responses.JSONResponse = Response  # type: ignore[attr-defined]
    starlette_routing.Route = Route  # type: ignore[attr-defined]
    starlette_routing.Mount = Route  # type: ignore[attr-defined]
    sys.modules.update({
        "starlette": starlette,
        "starlette.applications": starlette_applications,
        "starlette.requests": starlette_requests,
        "starlette.responses": starlette_responses,
        "starlette.routing": starlette_routing,
    })

    sys.modules["uvicorn"] = types.ModuleType("uvicorn")


try:
    server = importlib.import_module("transport.server")
except ModuleNotFoundError:
    _install_import_stubs()
    server = importlib.import_module("transport.server")


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        json_data: Any | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content if content or json_data is None else b"{}"
        self._json_data = json_data
        self._chunks = chunks if chunks is not None else [content]
        self.closed = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def read(self) -> bytes:
        return self.content

    def iter_bytes(self):
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class FakePodmanHTTP:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.request_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.post_calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        self.get_calls: list[str] = []
        self.sent_request: tuple[str, str, dict[str, Any]] | None = None
        self.put_response = FakeResponse()
        self.archive_response = FakeResponse()
        self.start_content = _demux_frame(b"transfer output")

    def request(self, method: str, path: str, **kwargs: Any) -> FakeResponse:
        self.request_calls.append((method, path, kwargs))
        if method == "PUT":
            return self.put_response
        return FakeResponse(json_data={"Id": "exec-1"})

    def post(self, path: str, **kwargs: Any) -> FakeResponse:
        self.post_calls.append((path, kwargs.get("json", {}), kwargs))
        return FakeResponse(content=self.start_content)

    def get(self, path: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append(path)
        return FakeResponse(json_data={"ExitCode": self.exit_code})

    def build_request(self, method: str, path: str, **kwargs: Any):
        request = (method, path, kwargs)
        self.sent_request = request
        return request

    def send(self, request: tuple[str, str, dict[str, Any]], **kwargs: Any):
        self.sent_request = request
        return self.archive_response


def _demux_frame(payload: bytes) -> bytes:
    return bytes([1, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def _podman_client(http: FakePodmanHTTP):
    client = object.__new__(server.PodmanClient)
    client._c = http
    return client


def _make_archive(name: str, payload: bytes, mode: str = "w") -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode=mode) as archive:
        member = tarfile.TarInfo(name)
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    return output.getvalue()


class PodmanPrimitiveTests(unittest.TestCase):
    def test_archive_put_uses_tar_body_and_pause_false(self) -> None:
        http = FakePodmanHTTP()
        client = _podman_client(http)
        body = b"generated outer tar"

        client.container_archive_put("gs-test", "/workspace", body)

        method, path, kwargs = http.request_calls[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(path, "/libpod/containers/gs-test/archive")
        self.assertEqual(kwargs["params"], {"path": "/workspace", "pause": "false"})
        self.assertEqual(kwargs["headers"], {"Content-Type": "application/x-tar"})
        self.assertEqual(kwargs["content"], body)
        self.assertTrue(http.put_response.closed)

    def test_archive_put_error_contains_status_and_body(self) -> None:
        http = FakePodmanHTTP()
        http.put_response = FakeResponse(413, b"archive body too large")
        client = _podman_client(http)

        with self.assertRaisesRegex(RuntimeError, r"413.*archive body too large"):
            client.container_archive_put("crew", "/workspace", b"tar")
        self.assertTrue(http.put_response.closed)

    def test_checked_exec_has_no_stdin_and_checks_exit_code(self) -> None:
        http = FakePodmanHTTP()
        client = _podman_client(http)

        output = client.container_exec_checked(
            "crew",
            ["python3", "-c", "fixed script"],
            env={"GA_TRANSFER_SOURCE": "/workspace/.stage/payload"},
        )

        spec = http.request_calls[0][2]["json"]
        self.assertEqual(output, "transfer output")
        self.assertNotIn("AttachStdin", spec)
        self.assertEqual(spec["Cmd"], ["python3", "-c", "fixed script"])
        self.assertEqual(spec["Env"], ["GA_TRANSFER_SOURCE=/workspace/.stage/payload"])
        self.assertEqual(http.get_calls, ["/libpod/exec/exec-1/json"])

    def test_checked_exec_reports_nonzero_output(self) -> None:
        http = FakePodmanHTTP(exit_code=17)
        http.start_content = _demux_frame(b"copy failed")
        client = _podman_client(http)

        with self.assertRaisesRegex(RuntimeError, r"17.*copy failed"):
            client.container_exec_checked("crew", ["python3", "-c", "fixed"])

    def test_archive_get_exposes_raw_stream_and_validates_errors(self) -> None:
        http = FakePodmanHTTP()
        archive = FakeResponse(chunks=[b"raw", b" tar"])
        http.archive_response = archive
        client = _podman_client(http)

        response = client.container_archive_get("crew", "/workspace/binary")
        self.assertIs(response, archive)
        self.assertEqual(
            http.sent_request,
            ("GET", "/libpod/containers/crew/archive", {"params": {"path": "/workspace/binary"}}),
        )
        self.assertFalse(archive.closed)
        self.assertEqual(b"".join(response.iter_bytes()), b"raw tar")
        response.close()
        self.assertTrue(archive.closed)

        failure = FakeResponse(404, b"missing file")
        http.archive_response = failure
        with self.assertRaisesRegex(RuntimeError, r"404.*missing file"):
            client.container_archive_get("crew", "/workspace/missing")
        self.assertTrue(failure.closed)


class RecordingTransferPodman:
    """Fake PodmanClient that applies the fixed transfer scripts locally."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.archive_calls: list[tuple[str, str, bytes]] = []
        self.exec_calls: list[tuple[str, list[str], dict[str, str]]] = []
        self.removed_stages: list[str] = []
        self.fail_transfer = False

    def container_archive_put(
        self,
        container: str,
        workspace: str,
        tar_body: bytes,
    ) -> None:
        self.archive_calls.append((container, workspace, tar_body))
        with tarfile.open(fileobj=io.BytesIO(tar_body), mode="r:") as archive:
            member = archive.next()
            assert member is not None
            payload = archive.extractfile(member)
            assert payload is not None
            self.files[f"{workspace.rstrip('/')}/{member.name}"] = payload.read()

    def container_exec_checked(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        values = dict(env or {})
        self.exec_calls.append((container, cmd, values))
        if cmd[2] == server._CLEANUP_TRANSFER_SCRIPT:
            self._remove_stage(values["GA_TRANSFER_STAGE"])
            return ""
        if self.fail_transfer:
            raise RuntimeError("copy failed")

        source = values["GA_TRANSFER_SOURCE"]
        payload = self.files[source]
        destination = Path(values["GA_TRANSFER_DEST"])
        if cmd[2] == server._RAW_TRANSFER_SCRIPT:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
            result = f"wrote {len(payload)} bytes to {destination}"
        else:
            destination.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=io.BytesIO(payload), mode="r|*") as archive:
                archive.extractall(destination, filter="data")
            result = f"unpacked to {destination}"
        self._remove_stage(values["GA_TRANSFER_STAGE"])
        return result

    def _remove_stage(self, stage: str) -> None:
        self.removed_stages.append(stage)
        for path in list(self.files):
            if path == stage or path.startswith(f"{stage}/"):
                del self.files[path]


class UploadRegressionTests(unittest.TestCase):
    def test_large_raw_upload_is_exact_and_payload_stays_out_of_exec_inputs(self) -> None:
        payload = bytes(range(256)) * 700
        self.assertGreater(len(base64.b64encode(payload)), 128 * 1024)
        fake = RecordingTransferPodman()

        with tempfile.TemporaryDirectory() as temporary:
            workspace = str(Path(temporary) / "workspace")
            destination = str(Path(workspace) / "nested" / "file.bin")
            result = server._transfer_upload(
                fake, "crew", workspace, destination, payload, unpack=False
            )

            self.assertIn(str(len(payload)), result)
            self.assertEqual(Path(destination).read_bytes(), payload)
            self.assertEqual(len(fake.archive_calls), 1)
            self.assertTrue(fake.removed_stages)
            for _container, command, env in fake.exec_calls:
                serialized = repr((command, env)).encode()
                self.assertNotIn(payload, serialized)

    def test_large_archive_upload_extracts_entries_and_removes_stage(self) -> None:
        payload = (b"archive payload" * 12000)[:180000]
        archive_body = _make_archive("tree/file.bin", payload, mode="w")
        self.assertGreater(len(base64.b64encode(archive_body)), 128 * 1024)
        fake = RecordingTransferPodman()

        with tempfile.TemporaryDirectory() as temporary:
            workspace = str(Path(temporary) / "workspace")
            destination = str(Path(workspace) / "tree")
            server._transfer_upload(
                fake, "crew", workspace, destination, archive_body, unpack=True
            )

            self.assertEqual(Path(destination, "tree", "file.bin").read_bytes(), payload)
            self.assertTrue(fake.removed_stages)
            command, env = fake.exec_calls[0][1:]
            self.assertEqual(command[0:2], ["python3", "-c"])
            self.assertEqual(env["GA_TRANSFER_DEST"], destination)

    def test_failed_exec_preserves_error_and_attempts_cleanup(self) -> None:
        fake = RecordingTransferPodman()
        fake.fail_transfer = True
        with tempfile.TemporaryDirectory() as temporary:
            workspace = str(Path(temporary) / "workspace")
            with self.assertRaisesRegex(RuntimeError, "copy failed"):
                server._transfer_upload(
                    fake,
                    "crew",
                    workspace,
                    str(Path(workspace) / "file.bin"),
                    b"small",
                    unpack=False,
                )
        self.assertTrue(fake.removed_stages)
        self.assertEqual(fake.exec_calls[-1][1][2], server._CLEANUP_TRANSFER_SCRIPT)


class BundleTransferPodman:
    """Run bundle transfer commands against a local temporary workspace."""

    def __init__(self) -> None:
        self.archive_calls: list[tuple[str, str, bytes]] = []
        self.exec_calls: list[tuple[str, list[str], dict[str, str]]] = []

    def container_archive_put(
        self,
        container: str,
        workspace: str,
        tar_body: bytes,
    ) -> None:
        self.archive_calls.append((container, workspace, tar_body))
        with tarfile.open(fileobj=io.BytesIO(tar_body), mode="r:") as archive:
            archive.extractall(workspace, filter="data")

    def container_exec_checked(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        values = dict(env or {})
        self.exec_calls.append((container, cmd, values))
        if cmd[:2] == ["python3", "-c"] and len(cmd) > 2:
            if cmd[2] == server._CLEANUP_TRANSFER_SCRIPT:
                shutil.rmtree(values["GA_TRANSFER_STAGE"], ignore_errors=True)
                return ""
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode:
            raise RuntimeError(output.strip() or f"command failed: {completed.returncode}")
        return output


class BundleUploadRegressionTests(unittest.TestCase):
    @staticmethod
    def _create_source_repo(root: Path) -> tuple[Path, bytes, list[str]]:
        repo = root / "source"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
        )
        commits: list[str] = []
        tracked = repo / "history.txt"
        for value in ("base\n", "second\n"):
            tracked.write_text(value)
            subprocess.run(["git", "add", "history.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", value.strip()], cwd=repo, check=True)
            commits.append(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                ).strip()
            )
        bundle_path = root / "source.bundle"
        subprocess.run(
            ["git", "bundle", "create", str(bundle_path), "--all"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        return repo, bundle_path.read_bytes(), commits

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_bundle_upload_clones_real_history_into_absent_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, bundle, commits = self._create_source_repo(root)
            workspace = root / "workspace"
            workspace.mkdir()
            destination = workspace / "nested" / "repo"
            fake = BundleTransferPodman()

            result = server._transfer_upload(
                fake,
                "crew",
                str(workspace),
                str(destination),
                bundle,
                unpack=False,
                bundle=True,
            )

            self.assertTrue(destination.joinpath(".git").is_dir())
            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=destination,
                    text=True,
                ).strip(),
                "2",
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=destination, text=True
                ).strip(),
                commits[-1],
            )
            self.assertTrue(
                any(call[1][:2] == ["git", "clone"] for call in fake.exec_calls)
            )
            self.assertFalse(list(workspace.glob(".kirocrew-transfer-*")))

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_bundle_upload_surfaces_occupied_destination_and_keeps_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _repo, bundle, _commits = self._create_source_repo(root)
            workspace = root / "workspace"
            workspace.mkdir()
            destination = workspace / "repo"
            destination.mkdir()
            existing = destination / "keep.txt"
            existing.write_text("do not replace\n")
            fake = BundleTransferPodman()

            with self.assertRaises(RuntimeError):
                server._transfer_upload(
                    fake,
                    "crew",
                    str(workspace),
                    str(destination),
                    bundle,
                    unpack=False,
                    bundle=True,
                )

            self.assertEqual(existing.read_text(), "do not replace\n")
            self.assertFalse(list(workspace.glob(".kirocrew-transfer-*")))


class DownloadRegressionTests(unittest.TestCase):
    def test_binary_archive_member_is_byte_exact_and_response_closes(self) -> None:
        payload = (b"\x80\xff\xfe" * (99415 // 3)) + b"\x00" * (99415 % 3)
        self.assertEqual(len(payload), 99415)
        expected_digest = hashlib.sha256(payload).hexdigest()
        archive_body = _make_archive("bundle.bin", payload)
        response = FakeResponse(
            chunks=[archive_body[i:i + 37] for i in range(0, len(archive_body), 37)]
        )

        stream = server._TarMemberStream(response, "repo/bundle.bin")
        downloaded = b"".join(stream)

        self.assertEqual(len(downloaded), 99415)
        self.assertEqual(hashlib.sha256(downloaded).hexdigest(), expected_digest)
        self.assertEqual(downloaded, payload)
        self.assertNotIn(b"\xef\xbf\xbd", downloaded)
        self.assertTrue(response.closed)

    def test_malformed_missing_and_nonregular_archives_close_response(self) -> None:
        cases = [
            b"not a tar stream",
            _make_archive("other.bin", b"payload"),
        ]
        directory = tarfile.TarInfo("bundle.bin")
        directory.type = tarfile.DIRTYPE
        directory_archive = io.BytesIO()
        with tarfile.open(fileobj=directory_archive, mode="w") as archive:
            archive.addfile(directory)
        cases.append(directory_archive.getvalue())

        for archive_body in cases:
            response = FakeResponse(chunks=[archive_body])
            with self.assertRaises(Exception):
                server._TarMemberStream(response, "repo/bundle.bin")
            self.assertTrue(response.closed)

    @unittest.skipUnless(shutil.which("git"), "git is required for this local regression")
    def test_binary_git_diff_remains_a_textual_notice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            binary = root / "bundle.bin"
            binary.write_bytes(b"\x00\xff\x01")
            subprocess.run(["git", "add", "bundle.bin"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
            binary.write_bytes(b"\x00\xff\x02")

            diff = subprocess.check_output(
                ["git", "diff", "HEAD", "--", "bundle.bin"], cwd=root
            )
            text = diff.decode("utf-8")
            self.assertIn("Binary files a/bundle.bin and b/bundle.bin differ", text)
            self.assertNotIn("\ufffd", text)
            self.assertNotIn(b"\x00\xff\x02", diff)


if __name__ == "__main__":
    unittest.main()
