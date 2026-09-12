# TRN-160 Design: files.py streaming transfer tests

## Test File

New file: `tests/unit/test_streaming_transfer.py`

## Import Setup

Use the existing `_install_import_stubs` bootstrap from `test_file_transfer.py` (which now registers `httpx2` in `sys.modules` as of TRN-155) before importing `transport.files`:

```python
from tests.unit.test_file_transfer import _install_import_stubs
_install_import_stubs()
import transport.files as files_mod
```

## Test Helpers

```python
def _make_response_chunks(chunks):
    resp = MagicMock()
    resp.iter_bytes.return_value = iter(chunks)
    return resp

def _make_tar_bytes(filename, content):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tf.addfile(info, io.BytesIO(content))
    return buf.getvalue()
```

## _ResponseChunkReader Tests (TestResponseChunkReader)

| Test | Setup | Assert |
|:-----|:------|:-------|
| single chunk | `[b"hello"]` | `read(-1)` == `b"hello"` |
| multiple chunks | `[b"foo", b"bar", b"baz"]` | `read(-1)` == `b"foobarbaz"` |
| sized read | `[b"abcdefgh"]` | `read(3)` == `b"abc"`, then `read(3)` == `b"def"`, then `read(-1)` == `b"gh"` |
| zero read | `[b"data"]` | `read(0)` == `b""` |
| empty stream | `[]` | `read(-1)` == `b""`, `read(5)` == `b""` |
| cross-boundary | `[b"ab", b"cd", b"ef"]` | `read(4)` == `b"abcd"`, `read(-1)` == `b"ef"` |
| partial then eof | `[b"abc"]` | `read(10)` == `b"abc"`, `read(1)` == `b""` |

## _TarMemberStream Tests (TestTarMemberStream)

| Test | Setup | Assert |
|:-----|:------|:-------|
| exact path | tar with `data.txt` | iteration yields `b"hello"` |
| basename match | tar with `data.txt`, request `/some/dir/data.txt` | finds by basename |
| missing member | tar with `other.txt`, request `missing.txt` | raises `ValueError` |
| empty archive | empty tar | raises `ValueError` |
| truncated | `b"not a tar file"` | raises any `Exception` |
| close idempotent | normal stream | `.close()` twice doesn't raise |
| context manager | normal stream | `with` block yields data, closes on exit |

## _transfer_upload Slash-Ref Tests (TestTransferUploadSlashRef)

Mock `container_exec_checked` side effects:
- **slash-ref case**: `rev-parse HEAD` → raises `RuntimeError`, `branch -r` → returns `"  origin/release/0.5.0\n"`, `checkout` → returns `""`
- **normal case**: all calls return `"abc1234\n"` (HEAD resolves)

Assert:
- slash-ref case: a `checkout` call appears in `container_exec_checked.call_args_list`
- normal case: no `checkout` call appears
