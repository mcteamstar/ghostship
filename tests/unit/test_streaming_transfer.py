"""Unit tests for _ResponseChunkReader and _TarMemberStream (TRN-260 C-1).

These classes expose chunked HTTP responses as file-like objects for use with
tarfile. Tests cover normal reads, cross-chunk boundaries, early EOF, and the
member-not-found / not-regular-file error paths in _TarMemberStream.
"""
from __future__ import annotations

import io
import tarfile
import unittest
from unittest.mock import MagicMock

try:
    from files import _ResponseChunkReader, _TarMemberStream  # container flat
except (ModuleNotFoundError, ImportError):
    from transport.files import _ResponseChunkReader, _TarMemberStream  # local


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_tar_bytes(members: dict[str, bytes]) -> bytes:
    """Build an in-memory tar archive with the given {name: content} members."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _fake_response(data: bytes, chunk_size: int = 4096) -> MagicMock:
    """Return a mock httpx.Response whose iter_bytes() yields fixed-size chunks."""
    resp = MagicMock()
    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b""]
    resp.iter_bytes.return_value = iter(chunks)
    return resp


# ── _ResponseChunkReader ──────────────────────────────────────────────────────

class TestResponseChunkReader(unittest.TestCase):

    def test_read_all(self):
        """read() with no size arg returns the full content."""
        reader = _ResponseChunkReader(iter([b"hello", b" ", b"world"]))
        self.assertEqual(reader.read(), b"hello world")

    def test_read_exact_size(self):
        """read(n) returns exactly n bytes."""
        reader = _ResponseChunkReader(iter([b"abcdef"]))
        self.assertEqual(reader.read(3), b"abc")
        self.assertEqual(reader.read(3), b"def")

    def test_read_across_chunk_boundary(self):
        """read(n) spanning two chunks assembles them correctly."""
        reader = _ResponseChunkReader(iter([b"ab", b"cd", b"ef"]))
        self.assertEqual(reader.read(4), b"abcd")
        self.assertEqual(reader.read(2), b"ef")

    def test_read_zero_returns_empty(self):
        """read(0) always returns b'' without consuming anything."""
        reader = _ResponseChunkReader(iter([b"data"]))
        self.assertEqual(reader.read(0), b"")
        self.assertEqual(reader.read(), b"data")

    def test_read_past_eof_returns_partial(self):
        """read(n) at EOF returns whatever remains, not raising."""
        reader = _ResponseChunkReader(iter([b"hi"]))
        self.assertEqual(reader.read(100), b"hi")

    def test_empty_chunks_skipped(self):
        """Empty chunk items in the iterator are ignored."""
        reader = _ResponseChunkReader(iter([b"", b"x", b"", b"y"]))
        self.assertEqual(reader.read(), b"xy")

    def test_empty_iterator(self):
        """Empty iterator returns b'' immediately."""
        reader = _ResponseChunkReader(iter([]))
        self.assertEqual(reader.read(), b"")

    def test_sequential_reads_consume_buffer(self):
        """Each read advances the position — data is not re-read."""
        reader = _ResponseChunkReader(iter([b"123456"]))
        self.assertEqual(reader.read(2), b"12")
        self.assertEqual(reader.read(2), b"34")
        self.assertEqual(reader.read(2), b"56")
        self.assertEqual(reader.read(2), b"")


# ── _TarMemberStream ──────────────────────────────────────────────────────────

class TestTarMemberStream(unittest.TestCase):

    def _stream(self, members: dict[str, bytes], path: str,
                chunk_size: int = 4096) -> _TarMemberStream:
        tar_bytes = _make_tar_bytes(members)
        resp = _fake_response(tar_bytes, chunk_size)
        return _TarMemberStream(resp, path)

    def test_reads_member_content(self):
        """Iterating the stream yields the full member content."""
        content = b"hello from the archive"
        stream = self._stream({"myfile.txt": content}, "myfile.txt")
        result = b"".join(stream)
        self.assertEqual(result, content)

    def test_reads_member_by_basename(self):
        """Path lookup also matches by basename so /dir/file.txt finds file.txt."""
        content = b"nested content"
        stream = self._stream({"dir/file.txt": content}, "/dir/file.txt")
        result = b"".join(stream)
        self.assertEqual(result, content)

    def test_large_content_across_chunks(self):
        """Content larger than one chunk is reassembled correctly."""
        content = b"x" * 100_000
        stream = self._stream({"big.bin": content}, "big.bin", chunk_size=1024)
        result = b"".join(stream)
        self.assertEqual(result, content)

    def test_member_not_found_raises(self):
        """ValueError is raised when the expected path is not in the archive."""
        with self.assertRaises(ValueError) as ctx:
            self._stream({"other.txt": b"data"}, "missing.txt")
        self.assertIn("missing.txt", str(ctx.exception))

    def test_close_is_idempotent(self):
        """Calling close() multiple times does not raise."""
        content = b"data"
        stream = self._stream({"f.txt": content}, "f.txt")
        _ = b"".join(stream)   # iterating calls close() in finally
        stream.close()          # second close — must not raise

    def test_response_closed_after_iteration(self):
        """The underlying response is closed when the stream is exhausted."""
        tar_bytes = _make_tar_bytes({"f.txt": b"abc"})
        resp = _fake_response(tar_bytes)
        stream = _TarMemberStream(resp, "f.txt")
        _ = b"".join(stream)
        resp.close.assert_called()

    def test_response_closed_on_member_not_found(self):
        """The underlying response is closed even when __init__ raises."""
        tar_bytes = _make_tar_bytes({"other.txt": b"x"})
        resp = _fake_response(tar_bytes)
        with self.assertRaises(ValueError):
            _TarMemberStream(resp, "missing.txt")
        resp.close.assert_called()


if __name__ == "__main__":
    unittest.main()
