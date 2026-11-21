"""Unit tests for transport/files.py — presigned URL signing/verification
and path-traversal boundary enforcement.

Design notes:
- GA_FILE_SECRET is set in the environment before the files module is imported
  so _load_or_create_file_secret() picks up the fixed test value.
- Tests access the module's private functions directly via monkeypatching or
  by importing the module with the env var already set.
- All I/O dependencies (PodmanClient, lifecycle, httpx2) are already stubbed
  by conftest.py's _install_transport_stubs call.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import os
import sys
import time
import unittest

# Fix GA_FILE_SECRET before any files.py import so _load_or_create_file_secret
# returns the test value rather than reading /data/ or generating a random one.
_TEST_FILE_SECRET = "test-file-secret-value-32chars!!"
os.environ["GA_FILE_SECRET"] = _TEST_FILE_SECRET

# Ensure transport stubs are installed (httpx2, starlette, etc.) before import.
# conftest does this at session scope; when running this file standalone we
# call it directly.
try:
    from tests.unit.conftest import _install_transport_stubs
    _install_transport_stubs()
except Exception:
    pass

try:
    import files as _files
except ModuleNotFoundError:
    from transport import files as _files


def _sign_manual(
    crew_id: str,
    path: str,
    expires: int,
    method: str = "GET",
    ref: str = "",
    flags: str = "",
) -> str:
    """Reproduce the HMAC signature the way files.py does it."""
    payload = f"{crew_id}:{path}:{expires}:{method}:{ref}:{flags}"
    return hmac.HMAC(
        _TEST_FILE_SECRET.encode(),
        payload.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()


class TestSignVerifyRoundTrip(unittest.TestCase):
    """_sign_file_url + _verify_file_token round-trip for GET and PUT."""

    def _future_expires(self) -> int:
        return int(time.time()) + 300

    def test_get_sign_verify_roundtrip(self):
        """A freshly-signed GET URL passes verification."""
        # Build a URL, then manually extract and verify the token.
        url = _files._sign_file_url("my-crew", "workspace/file.txt")
        # Parse sig and expires from the URL query string.
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            params["expires"],
            params["sig"],
        )
        self.assertTrue(result)

    def test_put_sign_verify_roundtrip(self):
        """A freshly-signed upload (POST) token passes verification."""
        url = _files._sign_upload_url("my-crew", "workspace/upload.tar")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        # mode=None means GET in verify; for POST we pass mode="" (plain write)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/upload.tar",
            params["expires"],
            params["sig"],
            mode="",  # plain write — no unpack/bundle flags
        )
        self.assertTrue(result)

    def test_get_token_rejected_for_put(self):
        """A GET token must be rejected when mode="".

        The payload format differs (GET encodes ref+bundle; POST encodes
        force/unpack/bundle) so a GET signature never matches a POST payload.
        """
        url = _files._sign_file_url("my-crew", "workspace/file.txt")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        # Try to use the GET sig for a POST verification (mode="")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            params["expires"],
            params["sig"],
            mode="",  # POST mode — different payload format
        )
        self.assertFalse(result)


class TestTamperedSignature(unittest.TestCase):
    """Tampered sig parameter → verification fails."""

    def test_modified_sig_rejected(self):
        url = _files._sign_file_url("my-crew", "workspace/data.bin")
        qs = url.split("?", 1)[1]
        params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
        tampered_sig = params["sig"][:-4] + "0000"
        result = _files._verify_file_token(
            "my-crew",
            "workspace/data.bin",
            params["expires"],
            tampered_sig,
        )
        self.assertFalse(result)

    def test_entirely_wrong_sig_rejected(self):
        expires = str(int(time.time()) + 300)
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            expires,
            "deadbeef" * 8,
        )
        self.assertFalse(result)


class TestExpiredToken(unittest.TestCase):
    """Tokens with a past expiry are rejected."""

    def test_expired_get_token_rejected(self):
        past_expires = int(time.time()) - 10  # already expired
        sig = _sign_manual("my-crew", "workspace/file.txt", past_expires, "GET")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/file.txt",
            str(past_expires),
            sig,
        )
        self.assertFalse(result)

    def test_expired_put_token_rejected(self):
        past_expires = int(time.time()) - 10
        sig = _sign_manual("my-crew", "workspace/upload.tar", past_expires, "POST", flags="")
        result = _files._verify_file_token(
            "my-crew",
            "workspace/upload.tar",
            str(past_expires),
            sig,
            mode="",
        )
        self.assertFalse(result)

    def test_non_integer_expires_rejected(self):
        result = _files._verify_file_token(
            "my-crew", "workspace/file.txt", "not-a-number", "deadbeef" * 8
        )
        self.assertFalse(result)


class TestSafeWorkspacePath(unittest.TestCase):
    """_safe_workspace_path path-traversal rejection."""

    def test_normal_path_resolves(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "subdir/file.txt")
            self.assertTrue(str(result).startswith(resolved_root))

    def test_path_traversal_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                _files._safe_workspace_path(tmpdir, "../escape/file.txt")

    def test_absolute_path_stripped_and_accepted(self):
        """An absolute raw_path has its leading '/' stripped and resolves inside root.

        _safe_workspace_path calls lstrip('/') on the raw path, so /etc/passwd
        becomes 'etc/passwd' which resolves inside the workspace root.
        This is by design: the function is meant for URL-path segments where a
        leading slash is just formatting, not a filesystem root escape.
        """
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "/etc/passwd")
            self.assertTrue(str(result).startswith(resolved_root))

    def test_deeply_nested_traversal_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                _files._safe_workspace_path(tmpdir, "a/b/../../../../../../etc/shadow")

    def test_valid_nested_path_accepted(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            resolved_root = str(Path(tmpdir).resolve())
            result = _files._safe_workspace_path(tmpdir, "a/b/c/file.txt")
            self.assertTrue(str(result).startswith(resolved_root))

    def test_double_dotdot_etc_passwd_rejected(self):
        """../../etc/passwd must raise ValueError because it resolves outside the workspace.

        TRN-284 task 5.2: Explicitly verify the canonical path-traversal probe
        used in security scanners is rejected by _safe_workspace_path.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                _files._safe_workspace_path(tmpdir, "../../etc/passwd")


# ─────────────────────────────────────────────────────────────────────────────
# T3 — TestFileGetHandler and TestFilePutHandler  (TRN-292)
# ─────────────────────────────────────────────────────────────────────────────

import asyncio
from unittest.mock import MagicMock, patch


def _async_run(coro):
    """Run a coroutine using a new event loop, then RESTORE a new event loop.

    Python 3.12 deprecates asyncio.get_event_loop() after asyncio.run() has
    been called (asyncio.run() closes and clears the thread's event loop).
    test_fleet.py uses asyncio.get_event_loop(), so we must not leave the
    event loop in a closed/absent state. We install a fresh loop after each
    run so downstream tests still find one.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        # Restore a fresh running loop so asyncio.get_event_loop() keeps working.
        asyncio.set_event_loop(asyncio.new_event_loop())

try:
    from starlette.requests import Request as StarletteRequest
except ImportError:
    # stub already installed via conftest; get it directly
    import sys as _sys
    StarletteRequest = _sys.modules["starlette.requests"].Request


class _FakeRequest:
    """Minimal request stub for _handle_file_get / _handle_file_put."""

    def __init__(self, crew_id: str, path: str, query_params: dict | None = None,
                 body_bytes: bytes = b"", headers: dict | None = None,
                 chunks: list[bytes] | None = None, stream_error: Exception | None = None):
        self.path_params = {"crew_id": crew_id, "path": path}
        self.query_params = query_params or {}
        self._body = body_bytes
        self.headers = headers if headers is not None else {"content-length": str(len(body_bytes))}
        self._chunks = chunks if chunks is not None else [body_bytes]
        self._stream_error = stream_error

    async def stream(self):
        for chunk in self._chunks:
            yield chunk
        if self._stream_error is not None:
            raise self._stream_error


def _valid_get_params(crew_id: str, path: str) -> dict:
    """Build a valid (non-expired) query-param dict for _handle_file_get."""
    url = _files._sign_file_url(crew_id, path)
    qs = url.split("?", 1)[1]
    return dict(p.split("=", 1) for p in qs.split("&") if "=" in p)


def _valid_put_params(crew_id: str, path: str) -> dict:
    """Build a valid (non-expired) query-param dict for _handle_file_put."""
    url = _files._sign_upload_url(crew_id, path)
    qs = url.split("?", 1)[1]
    return dict(p.split("=", 1) for p in qs.split("&") if "=" in p)


class TestTransferUploadDispatch(unittest.TestCase):
    """Every mutation mode is delegated to the disposable worker script."""

    def test_upload_modes_use_confined_transfer_script(self):
        workspace = "/workspace"
        destination = "/workspace/nested/destination"
        stage = "/workspace/.kirocrew-transfer-test"
        staged_file = f"{stage}/payload"
        cases = [
            (False, False, False, []),
            (True, False, False, ["--unpack"]),
            (False, True, True, ["--bundle", "--force"]),
        ]
        for unpack, bundle, force, flags in cases:
            with self.subTest(unpack=unpack, bundle=bundle, force=force):
                podman = MagicMock()
                podman.worker_run.return_value = b"transfer complete"
                handed_off = []
                podman.container_archive_put.side_effect = (
                    lambda *args, **kwargs: handed_off.append(b"".join(args[2]))
                )
                outer_tar = io.BytesIO(b"outer tar")
                with patch.object(
                    _files,
                    "_build_outer_transfer_tar",
                    return_value=(stage, staged_file, outer_tar, 9),
                ):
                    result = _files._transfer_upload(
                        podman,
                        "crew-container",
                        workspace,
                        destination,
                        b"payload",
                        unpack,
                        bundle,
                        force,
                        volume_name="gs-vol-crew",
                    )
                self.assertEqual(result, "transfer complete")
                put_args, put_kwargs = podman.container_archive_put.call_args
                self.assertEqual(put_args[:2], ("crew-container", workspace))
                self.assertEqual(put_kwargs, {"content_length": 9})
                self.assertEqual(handed_off, [b"outer tar"])
                podman.worker_run.assert_called_once_with(
                    "gs-vol-crew",
                    ["python3", f"{_files.SCRIPTS_DIR}/transfer_raw.py", *flags],
                    env={
                        "GA_TRANSFER_SOURCE": f"{_files.WORKER_MOUNT}/.kirocrew-transfer-test/payload",
                        "GA_TRANSFER_DEST": f"{_files.WORKER_MOUNT}/nested/destination",
                        "GA_TRANSFER_STAGE": f"{_files.WORKER_MOUNT}/.kirocrew-transfer-test",
                        "GA_TRANSFER_WORKSPACE": _files.WORKER_MOUNT,
                        "GA_TRANSFER_MAX_ARCHIVE_BYTES": str(_files.cfg.ga_max_archive_bytes),
                        "GA_TRANSFER_MAX_ARCHIVE_MEMBERS": str(_files.cfg.ga_max_archive_members),
                        "GA_TRANSFER_BUNDLE_STORAGE_ROOT": _files.BUNDLE_STORAGE_ROOT,
                        "GA_TRANSFER_BUNDLE_STORAGE_LIMIT_BYTES": str(
                            _files.cfg.ga_max_bundle_storage_bytes
                        ),
                    },
                    writable=True,
                    tmpfs_size_bytes=(
                        _files.cfg.ga_max_bundle_storage_bytes if bundle else None
                    ),
                )

    def test_stage_fallback_cleanup_receives_workspace(self):
        podman = MagicMock()
        _files._cleanup_transfer_stage(
            podman,
            "crew-container",
            "/workspace/.kirocrew-transfer-test",
            "/workspace",
        )
        podman.container_exec_checked.assert_called_once_with(
            "crew-container",
            ["python3", f"{_files.SCRIPTS_DIR}/transfer_cleanup.py"],
            env={
                "GA_TRANSFER_STAGE": "/workspace/.kirocrew-transfer-test",
                "GA_TRANSFER_WORKSPACE": "/workspace",
            },
        )

    def test_archive_handoff_failure_closes_host_tar_and_cleans_crew_stage(self):
        outer_tar = io.BytesIO(b"partial tar")
        podman = MagicMock()
        podman.container_archive_put.side_effect = RuntimeError("handoff failed")
        with patch.object(
            _files,
            "_build_outer_transfer_tar",
            return_value=("/workspace/.stage", "/workspace/.stage/payload", outer_tar, 11),
        ), patch.object(_files, "_cleanup_transfer_stage") as cleanup:
            with self.assertRaisesRegex(RuntimeError, "handoff failed"):
                _files._transfer_upload(
                    podman, "gs-crew", "/workspace", "/workspace/file", b"x", False
                )
        self.assertTrue(outer_tar.closed)
        cleanup.assert_called_once_with(
            podman, "gs-crew", "/workspace/.stage", "/workspace"
        )

    def test_worker_budget_failure_becomes_http_budget_error(self):
        try:
            from podman import WorkerCommandError
        except ModuleNotFoundError:
            from transport.podman import WorkerCommandError
        podman = MagicMock()
        podman.worker_run.side_effect = WorkerCommandError(
            3, "TRANSFER_BUDGET_EXCEEDED: archive output limit"
        )
        outer_tar = io.BytesIO(b"outer tar")
        with patch.object(
            _files,
            "_build_outer_transfer_tar",
            return_value=("/workspace/.stage", "/workspace/.stage/payload", outer_tar, 9),
        ), patch.object(_files, "_cleanup_transfer_stage"):
            with self.assertRaises(_files.UploadBudgetExceeded):
                _files._transfer_upload(
                    podman,
                    "gs-crew",
                    "/workspace",
                    "/workspace/file",
                    b"x",
                    False,
                    volume_name="gs-vol-crew",
                )


class TestFileGetHandler(unittest.TestCase):
    """_handle_file_get: GET handler status-code contract (FG1–FG5)."""

    def _get(self, crew_id: str, path: str, query_params: dict | None = None):
        req = _FakeRequest(crew_id, path, query_params)
        return _async_run(_files._handle_file_get(req))

    # ── FG1 — expired token → 403 ─────────────────────────────────────────

    def test_fg1_expired_token_403(self):
        """FG1: expired token → 403 Forbidden."""
        import time as _time
        past = str(int(_time.time()) - 10)
        import hashlib as _hashlib, hmac as _hmac
        payload = f"test-crew:workspace/file.txt:{past}:GET::"
        sig = _hmac.HMAC(
            _TEST_FILE_SECRET.encode(),
            payload.encode(),
            digestmod=_hashlib.sha256,
        ).hexdigest()
        resp = self._get("test-crew", "workspace/file.txt",
                         {"expires": past, "sig": sig})
        self.assertEqual(resp.status_code, 403)

    # ── FG2 — invalid crew_id format → 400 ───────────────────────────────

    def test_fg2_invalid_crew_id_400(self):
        """FG2: crew_id 'INVALID_CREW!!' fails CREW_ID_RE → 400."""
        resp = self._get("INVALID_CREW!!", "file.txt")
        self.assertEqual(resp.status_code, 400)

    # ── FG3 — missing crew (KeyError from _require_crew) → 404 ───────────

    def test_fg3_missing_crew_404(self):
        """FG3: _require_crew raises KeyError → 404."""
        params = _valid_get_params("test-crew", "workspace/file.txt")
        with patch.object(_files._lifecycle, "_require_crew",
                          side_effect=KeyError("test-crew")):
            resp = self._get("test-crew", "workspace/file.txt", params)
        self.assertEqual(resp.status_code, 404)

    # ── FG4 — running crew, plain file → 200 ─────────────────────────────

    def test_fg4_running_crew_plain_file_200(self):
        """FG4: valid token, crew running, plain file served → 200."""
        from unittest.mock import MagicMock, patch
        params = _valid_get_params("test-crew", "workspace/file.txt")

        fake_crew = {"container": "gs-test-crew", "status": "running"}
        fake_podman = MagicMock()
        fake_podman.container_is_running.return_value = True

        # _crew_api for the running path: exec returns file bytes via archive API
        import io, tarfile as _tarfile

        # Build a tar archive containing the file
        buf = io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as t:
            content = b"hello world"
            info = _tarfile.TarInfo(name="workspace/file.txt")
            info.size = len(content)
            t.addfile(info, io.BytesIO(content))
        buf.seek(0)

        fake_archive_resp = MagicMock()
        fake_archive_resp.iter_bytes.return_value = iter([buf.read()])
        fake_podman.container_archive_get.return_value = fake_archive_resp

        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"

        with patch.object(_files._lifecycle, "_require_crew",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew",
                          return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=fake_podman):
            resp = self._get("test-crew", "workspace/file.txt", params)
        self.assertEqual(resp.status_code, 200)

    # ── FG5 — stopped crew, archive API path → 200 (not 404) ─────────────

    def test_fg5_stopped_crew_archive_api_200(self):
        """FG5: stopped crew serves file via archive API → 200, not 404."""
        params = _valid_get_params("test-crew", "workspace/file.txt")

        fake_crew = {"container": "gs-test-crew", "status": "stopped"}
        fake_podman = MagicMock()
        fake_podman.container_is_running.return_value = False

        import io, tarfile as _tarfile
        buf = io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as t:
            content = b"stopped file"
            info = _tarfile.TarInfo(name="workspace/file.txt")
            info.size = len(content)
            t.addfile(info, io.BytesIO(content))
        buf.seek(0)

        fake_archive_resp = MagicMock()
        fake_archive_resp.iter_bytes.return_value = iter([buf.read()])
        fake_podman.container_archive_get.return_value = fake_archive_resp

        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"

        with patch.object(_files._lifecycle, "_require_crew",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew",
                          return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=fake_podman):
            resp = self._get("test-crew", "workspace/file.txt", params)
        self.assertEqual(resp.status_code, 200)


class TestFilePutHandler(unittest.TestCase):
    """_handle_file_put: PUT handler status-code contract (FP1–FP5)."""

    def _put(self, crew_id: str, path: str, query_params: dict | None = None,
             body: bytes = b"content", headers: dict | None = None,
             chunks: list[bytes] | None = None,
             stream_error: Exception | None = None):
        req = _FakeRequest(
            crew_id, path, query_params, body_bytes=body, headers=headers,
            chunks=chunks, stream_error=stream_error,
        )
        return _async_run(_files._handle_file_put(req))

    # ── FP1 — expired token → 403 ─────────────────────────────────────────

    def test_fp1_expired_token_403(self):
        """FP1: expired PUT token → 403 Forbidden."""
        import time as _time
        past = str(int(_time.time()) - 10)
        import hashlib as _hashlib, hmac as _hmac
        # mode="" means plain PUT; flags=""
        payload = f"test-crew:workspace/file.txt:{past}:POST::"
        sig = _hmac.HMAC(
            _TEST_FILE_SECRET.encode(),
            payload.encode(),
            digestmod=_hashlib.sha256,
        ).hexdigest()
        resp = self._put("test-crew", "workspace/file.txt",
                         {"expires": past, "sig": sig})
        self.assertEqual(resp.status_code, 403)

    # ── FP2 — invalid crew_id → 400 ──────────────────────────────────────

    def test_fp2_invalid_crew_id_400(self):
        """FP2: crew_id contains uppercase/special chars → 400."""
        resp = self._put("BAD_CREW!", "file.txt")
        self.assertEqual(resp.status_code, 400)

    # ── FP3 — empty body → 400 ───────────────────────────────────────────

    def test_fp3_empty_body_400(self):
        """FP3: empty body with otherwise valid token → 400."""
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        with patch.object(_files._lifecycle, "_require_crew",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running",
                          return_value=fake_crew):
            resp = self._put("test-crew", "workspace/file.txt", params, body=b"")
        self.assertEqual(resp.status_code, 400)

    # ── FP4 — successful plain upload → 200 ──────────────────────────────

    def test_fp4_successful_upload_200(self):
        """FP4: valid token, body present, _transfer_upload succeeds → 200."""
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"

        with patch.object(_files._lifecycle, "_require_crew",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew",
                          return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=MagicMock()), \
             patch.object(_files, "_transfer_upload",
                          return_value="wrote to /workspace/file.txt"):
            resp = self._put("test-crew", "workspace/file.txt", params,
                             body=b"hello data")
        self.assertEqual(resp.status_code, 200)

    # ── FP5 — _transfer_upload raises → 500 ──────────────────────────────

    def test_fp5_transfer_upload_raises_500(self):
        """FP5: _transfer_upload raises RuntimeError → 500."""
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"

        with patch.object(_files._lifecycle, "_require_crew",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running",
                          return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew",
                          return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=MagicMock()), \
             patch.object(_files, "_transfer_upload",
                          side_effect=RuntimeError("upload failed")):
            resp = self._put("test-crew", "workspace/file.txt", params,
                             body=b"some data")
        self.assertEqual(resp.status_code, 500)

    def test_declared_upload_over_limit_returns_413_before_reading(self):
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        with patch.object(_files.cfg, "ga_max_upload_bytes", 4), \
             patch.object(_files._lifecycle, "_require_crew", return_value=fake_crew), \
             patch.object(_files, "_transfer_upload") as transfer:
            resp = self._put(
                "test-crew", "workspace/file.txt", params,
                headers={"content-length": "5"}, chunks=[b"not read"],
            )
        self.assertEqual(resp.status_code, 413)
        transfer.assert_not_called()

    def test_actual_upload_over_limit_without_length_returns_413(self):
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        with patch.object(_files.cfg, "ga_max_upload_bytes", 4), \
             patch.object(_files._lifecycle, "_require_crew", return_value=fake_crew), \
             patch.object(_files, "_transfer_upload") as transfer:
            resp = self._put(
                "test-crew", "workspace/file.txt", params,
                headers={}, chunks=[b"1234", b"5"],
            )
        self.assertEqual(resp.status_code, 413)
        transfer.assert_not_called()

    def test_missing_length_exact_limit_streams_to_transfer(self):
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"

        def capture_upload(*args, **kwargs):
            self.assertEqual(args[4].read(), b"1234")
            self.assertEqual(kwargs["body_size"], 4)
            return "ok"

        with patch.object(_files.cfg, "ga_max_upload_bytes", 4), \
             patch.object(_files._lifecycle, "_require_crew", return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running", return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew", return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=MagicMock()), \
             patch.object(_files, "_transfer_upload", side_effect=capture_upload):
            resp = self._put(
                "test-crew", "workspace/file.txt", params,
                headers={}, chunks=[b"12", b"34"],
            )
        self.assertEqual(resp.status_code, 200)

    def test_disconnect_closes_host_stage_and_does_not_handoff(self):
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        host_stage = io.BytesIO()
        with patch.object(_files._lifecycle, "_require_crew", return_value=fake_crew), \
             patch.object(_files.tempfile, "TemporaryFile", return_value=host_stage), \
             patch.object(_files, "_transfer_upload") as transfer:
            resp = self._put(
                "test-crew", "workspace/file.txt", params,
                headers={}, chunks=[b"partial"],
                stream_error=RuntimeError("client disconnected"),
            )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(host_stage.closed)
        transfer.assert_not_called()

    def test_transfer_budget_failure_returns_413(self):
        params = _valid_put_params("test-crew", "workspace/file.txt")
        fake_crew = {"container": "gs-test-crew", "status": "running"}
        fake_crew_obj = MagicMock()
        fake_crew_obj.container = "gs-test-crew"
        with patch.object(_files._lifecycle, "_require_crew", return_value=fake_crew), \
             patch.object(_files._lifecycle, "_ensure_crew_running", return_value=fake_crew), \
             patch.object(_files._lifecycle, "_to_crew", return_value=fake_crew_obj), \
             patch.object(_files, "_get_podman", return_value=MagicMock()), \
             patch.object(
                 _files, "_transfer_upload",
                 side_effect=_files.UploadBudgetExceeded("archive output limit"),
             ):
            resp = self._put("test-crew", "workspace/file.txt", params)
        self.assertEqual(resp.status_code, 413)


if __name__ == "__main__":
    unittest.main()
