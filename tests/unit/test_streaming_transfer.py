"""Unit tests for transport.files streaming classes (TRN-160).

Covers _ResponseChunkReader, _TarMemberStream error paths, and the
_transfer_upload slash-ref workaround path.
"""
from __future__ import annotations

import io
import tarfile
import unittest
from unittest.mock import MagicMock

# Install httpx2/mcp/starlette stubs before importing any transport module.
# _stubs.py registers httpx2 alongside httpx as of TRN-155.
from tests.unit.test_file_transfer import _install_import_stubs
_install_import_stubs()

import transport.files as files_mod  # noqa: E402 — stubs must be installed first


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response_chunks(chunks: list[bytes]) -> MagicMock:
    resp = MagicMock()
    resp.iter_bytes.return_value = iter(chunks)
    return resp


def _make_tar_bytes(filename: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _ResponseChunkReader
# ---------------------------------------------------------------------------

class TestResponseChunkReader(unittest.TestCase):

    def _make(self, chunks: list[bytes]):
        resp = _make_response_chunks(chunks)
        return files_mod._ResponseChunkReader(resp.iter_bytes())

    def test_read_all_single_chunk(self):
        r = self._make([b"hello world"])
        self.assertEqual(r.read(-1), b"hello world")

    def test_read_all_multiple_chunks(self):
        r = self._make([b"foo", b"bar", b"baz"])
        self.assertEqual(r.read(-1), b"foobarbaz")

    def test_read_sized(self):
        r = self._make([b"abcdefgh"])
        self.assertEqual(r.read(3), b"abc")
        self.assertEqual(r.read(3), b"def")
        self.assertEqual(r.read(-1), b"gh")

    def test_read_zero(self):
        r = self._make([b"data"])
        self.assertEqual(r.read(0), b"")

    def test_read_empty_stream(self):
        r = self._make([])
        self.assertEqual(r.read(-1), b"")
        self.assertEqual(r.read(5), b"")

    def test_read_across_chunk_boundary(self):
        r = self._make([b"ab", b"cd", b"ef"])
        self.assertEqual(r.read(4), b"abcd")
        self.assertEqual(r.read(-1), b"ef")

    def test_partial_read_then_eof(self):
        r = self._make([b"abc"])
        self.assertEqual(r.read(10), b"abc")   # request more than available
        self.assertEqual(r.read(1), b"")        # nothing left


# ---------------------------------------------------------------------------
# _TarMemberStream
# ---------------------------------------------------------------------------

class TestTarMemberStream(unittest.TestCase):

    def _make(self, filename: str, content: bytes, request_path: str):
        tar_bytes = _make_tar_bytes(filename, content)
        resp = MagicMock()
        resp.iter_bytes.return_value = iter([tar_bytes])
        return files_mod._TarMemberStream(resp, request_path)

    def test_read_member_by_exact_path(self):
        stream = self._make("data.txt", b"hello", "data.txt")
        self.assertEqual(b"".join(stream), b"hello")

    def test_read_member_by_basename(self):
        """Member can be found even when expected_path has a directory prefix."""
        stream = self._make("data.txt", b"world", "/some/dir/data.txt")
        self.assertEqual(b"".join(stream), b"world")

    def test_missing_member_raises(self):
        tar_bytes = _make_tar_bytes("other.txt", b"x")
        resp = MagicMock()
        resp.iter_bytes.return_value = iter([tar_bytes])
        with self.assertRaises(ValueError):
            files_mod._TarMemberStream(resp, "missing.txt")

    def test_empty_archive_raises(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w"):
            pass
        resp = MagicMock()
        resp.iter_bytes.return_value = iter([buf.getvalue()])
        with self.assertRaises(ValueError):
            files_mod._TarMemberStream(resp, "any.txt")

    def test_truncated_tar_raises(self):
        resp = MagicMock()
        resp.iter_bytes.return_value = iter([b"not a tar file at all"])
        with self.assertRaises(Exception):
            files_mod._TarMemberStream(resp, "file.txt")

    def test_close_idempotent(self):
        stream = self._make("f.txt", b"data", "f.txt")
        stream.close()
        stream.close()  # must not raise

    def test_context_manager(self):
        """_TarMemberStream has a close() method but no context manager protocol —
        verify data is readable and close works without error."""
        tar_bytes = _make_tar_bytes("f.txt", b"ctx")
        resp = MagicMock()
        resp.iter_bytes.return_value = iter([tar_bytes])
        stream = files_mod._TarMemberStream(resp, "f.txt")
        data = b"".join(stream)
        stream.close()
        self.assertEqual(data, b"ctx")


# ---------------------------------------------------------------------------
# _transfer_upload slash-ref workaround
# ---------------------------------------------------------------------------

class TestTransferUploadSlashRef(unittest.TestCase):

    def _make_podman_slash_ref(self) -> MagicMock:
        """Simulate a clone that leaves an empty working tree (rev-parse HEAD fails)."""
        podman = MagicMock()

        def _exec(container, cmd, **kwargs):
            joined = " ".join(cmd)
            if "rev-parse" in joined and "HEAD" in joined:
                raise RuntimeError("fatal: ambiguous argument 'HEAD'")
            if "branch" in joined and "-r" in joined:
                return "  origin/release/0.5.0\n  origin/HEAD -> origin/main\n"
            return ""

        podman.container_exec_checked.side_effect = _exec
        return podman

    def _call(self, podman):
        """Call _transfer_upload with the correct signature, patching internals."""
        import unittest.mock as mock
        # Patch _build_outer_transfer_tar to avoid needing real tar/stage logic
        with mock.patch.object(files_mod, "_build_outer_transfer_tar",
                               return_value=("/stage", "/stage/bundle.bundle", b"tar")), \
             mock.patch.object(files_mod, "_cleanup_transfer_stage"):
            files_mod._transfer_upload(
                podman,
                container="test-container",
                workspace="/workspace",
                destination="/workspace/repo",
                body=b"fake bundle bytes",
                unpack=False,
                bundle=True,
            )

    def test_slash_ref_triggers_checkout(self):
        """When rev-parse HEAD fails after clone, branch checkout is attempted."""
        podman = self._make_podman_slash_ref()
        self._call(podman)
        calls = [str(c) for c in podman.container_exec_checked.call_args_list]
        self.assertTrue(
            any("checkout" in c for c in calls),
            f"Expected a checkout call, got: {calls}",
        )

    def test_normal_head_skips_checkout(self):
        """When HEAD resolves normally, no extra checkout is performed."""
        podman = MagicMock()
        podman.container_exec_checked.return_value = "abc1234\n"
        self._call(podman)
        calls = [str(c) for c in podman.container_exec_checked.call_args_list]
        self.assertFalse(
            any("checkout" in c for c in calls),
            f"Unexpected checkout call: {calls}",
        )


if __name__ == "__main__":
    unittest.main()
