# TRN-292 Design — Test Coverage for Batch, File Transfer, and Security Primitives

## Overview

Three test groups, one per coverage gap. All use `unittest.TestCase` to match the existing test suite style; pytest is the runner. No new production files are created. All mocking follows the established module-patching pattern from `test_lifecycle.py` (patch at the transport module attribute, not at the call site).

---

## C-1: Batch Dispatch and Pickup Tests

### Source under test

`transport/lifecycle.py` — `_dispatch_batch` (line 2850) and `_pickup_batch` (line 2716).

### Test file

Add to `tests/unit/test_lifecycle.py`, or create `tests/unit/test_batch.py` if the existing file exceeds ~1 500 lines at time of implementation. Class names are the same either way.

### Collaborators and what to mock

`_dispatch_batch` uses three internal collaborators that must be patched at `transport.lifecycle.*`:

| Symbol | Patch target | What the stub does |
|---|---|---|
| `_require_crew` | `transport.lifecycle._require_crew` | Returns a minimal crew dict `{"gateway": "http://localhost:9099", "container": "gs-test", "status": "running"}` |
| `_ensure_crew_running` | `transport.lifecycle._ensure_crew_running` | Returns its first argument unchanged (crew already running) |
| `_resolve_dispatch_slot` | `transport.lifecycle._resolve_dispatch_slot` | Returns `(None, None)` (headless, no shared session) |
| `_crew_api_with_recovery` | `transport.lifecycle._crew_api_with_recovery` | Scripted per scenario: success returns `{"id": "task-001"}`, failure raises `CrewUnresponsiveError` |
| `_write_batch` | `transport.lifecycle._write_batch` | Captured via `MagicMock()` so test asserts `status` arg |

`_pickup_batch` takes injected callables so no patching is needed for its core logic — pass in mock functions directly:

| Parameter | What the stub does |
|---|---|
| `pickup_single` | Returns a scripted dict per task_id; scriptable per scenario |
| `read_all_mail_counts` | Returns `{"admiral": 0}` (baseline) for steady-state tests; returns `{"admiral": 1}` on second call for the admiral-mail early-return scenario |
| `update_batch_status` | `MagicMock()` — asserted called with `"complete"` when all done |

### Test class: `TestBatchDispatch`

**D1 — successful full batch:** 2-task batch, `_crew_api_with_recovery` returns `{"id": "task-001"}` then `{"id": "task-002"}`. Assert `response["status"] == "dispatched"`, `response["batch_id"]` is a non-empty string, `response["task_ids"] == ["task-001", "task-002"]`, `_write_batch` called once with `status="pending"`.

**D2 — partial batch mid-dispatch:** 2-task batch, first spawn succeeds (`{"id": "task-001"}`), second raises `CrewUnresponsiveError("gateway down")`. Assert `response["status"] == "partial"`, `response["task_ids"] == ["task-001"]`, `response["error"]` contains `"gateway down"`, `_write_batch` called once with `status="partial"`.

**D3 — spawn returns no task id:** `_crew_api_with_recovery` returns `{}` (no `"id"` key). Assert `response["status"] == "partial"`, `response["error"]` contains `"no task id"`.

**D4 — batch too small (1 task):** Call `_dispatch_batch(tasks=["only one"], ...)`. Assert the returned dict contains `"error"` mentioning `"at least 2"`.

**D5 — batch too large:** Set `GA_BATCH_MAX_TASKS=2` via `os.environ`; call with 3 tasks. Assert `"error"` contains `"exceeds maximum"`. Restore env in `tearDown` / `addCleanup`.

**D6 — crew not found:** `_require_crew` raises `ValueError("crew not found")`. Assert `response["error"]` is non-empty.

### Test class: `TestBatchPickup`

State machine: `pickup_single` is scripted by passing a `dict[task_id -> list[dict]]` where each call pops the next response.

**P1 — all done on first poll:** Two task_ids, both `pickup_single` calls return `{"done": True, ...}`. Assert `result["done"] is True`, `result["completed_tasks"] == 2`, `result["total_tasks"] == 2`, `update_batch_status` called with `(crew_id, batch_id, "complete")`.

**P2 — snapshot mode (timeout=0):** One done, one pending. Assert `result["done"] is False`, returns immediately (no sleep), `result["completed_tasks"] == 1`.

**P3 — timeout before all done:** `timeout_secs=3`, only one task ever done. Assert `result["done"] is False`, `result.get("reason") == "timeout"`. Patch `time.sleep` and `time.monotonic` to simulate expiry without real blocking.

**P4 — admiral-mail early return:** `timeout_secs=30`; `read_all_mail_counts` returns `{"admiral": 0}` on first call, `{"admiral": 1}` on second. Assert `result.get("reason") == "admiral_mail"` and `result["done"] is False`.

**P5 — lost task_id normalisation:** One task_id; `pickup_single` returns `{"error": "404 not found", "done": False}`. Assert the result for that task_id has `"lost": True` and `result["done"] is False`.

**P6 — empty task list:** `_pickup_batch(task_ids=[], ...)`. Assert `result["total_tasks"] == 0`, `result["done"] is False` (guard against `total > 0` being False when total=0).

---

## C-2: File Transfer Handler Tests

### Source under test

`transport/files.py` — `_handle_file_get` (line 517) and `_handle_file_put` (line 741).

### Test file

Add to `tests/unit/test_files.py`. The existing `TestSignVerifyRoundTrip` class already lives there; new classes are appended.

### Collaborators and what to mock

The handlers are `async def` functions that take a Starlette `Request` and return a Starlette `Response`. They are tested via `asyncio.run()` (or `unittest.IsolatedAsyncioTestCase`) with a fake request object.

The `conftest.py` starlette stub already provides `PlainTextResponse` and `StreamingResponse`. These handlers also call:

| Symbol | Patch target | What the stub does |
|---|---|---|
| `_verify_file_token` | `transport.files._verify_file_token` | Scriptable: `True` for valid, `False` for expired/invalid |
| `_lifecycle._require_crew` | `transport.files._lifecycle._require_crew` | Returns minimal crew dict or raises `KeyError` for missing crew |
| `_lifecycle._ensure_crew_running` | `transport.files._lifecycle._ensure_crew_running` | Returns crew dict unchanged |
| `_lifecycle._to_crew` | `transport.files._lifecycle._to_crew` | Returns a minimal crew object with `.container = "gs-test"` |
| `_get_podman` | `transport.files._get_podman` | Returns `FakePodmanClient()` |
| `podman.container_is_running` | Method on the fake | Scriptable True/False per scenario |
| `podman.container_archive_get` | Method on the fake | Scriptable per scenario |
| `_transfer_upload` | `transport.files._transfer_upload` | Returns `"wrote to /path"` or raises `Exception` |

**Fake request factory:** Build a minimal request stub (similar to the conftest `Request` stub) with:
- `request.path_params["crew_id"]` and `request.path_params["path"]`
- `request.query_params` (dict-like, with `get()`)
- `request.body()` returning a coroutine that yields `b"file content"`

### Test class: `TestFileGetHandler`

**FG1 — expired token rejected with 403:** `_verify_file_token` returns `False`. Assert response `status_code == 403`.

**FG2 — invalid crew_id format rejected with 400:** Pass a `crew_id` containing spaces or slashes (fails `CREW_ID_RE`). Assert `status_code == 400`.

**FG3 — missing crew returns 404:** `_verify_file_token` returns `True`; `_lifecycle._require_crew` raises `KeyError`. Assert `status_code == 404`.

**FG4 — running crew, plain file served:** `_verify_file_token` True, crew running, `podman.container_archive_get` returns a mock archive response. Assert `status_code == 200`.

**FG5 — stopped crew, plain file served via archive API:** `container_is_running` returns `False`. Assert the handler falls through to the stopped-crew path and returns `status_code == 200` (not 404).

### Test class: `TestFilePutHandler`

**FP1 — expired token rejected with 403:** `_verify_file_token` returns `False`. Assert `status_code == 403`.

**FP2 — invalid crew_id rejected with 400:** Malformed `crew_id`. Assert `status_code == 400`.

**FP3 — empty body rejected with 400:** `request.body()` returns `b""`. Assert `status_code == 400`.

**FP4 — successful plain-file upload:** `_verify_file_token` True, body non-empty, `_transfer_upload` returns `"wrote to /workspace/file.txt"`. Assert `status_code == 200`.

**FP5 — upload exception surfaces as 500:** `_transfer_upload` raises `Exception("disk full")`. Assert `status_code == 500`.

---

## H-6: Security Primitive Tests

### Source under test

`transport/security.py` — `generate_csp_nonce` (line 496), `needs_rehash` (line 271), `encode_html_text` (line 473), `encode_html_attr` (line 478), `encode_url_component` (line 483).

### Test file

Add to `tests/unit/test_security.py`. The existing classes (`TestHashPassword`, `TestThrottle`, `TestSessionStore`, `TestValidateStr`, `TestSecretRedactionFilter`) are untouched.

### Test class: `TestCspNonce`

**N1 — length:** `generate_csp_nonce()` returns a string of at least 16 characters. (`secrets.token_urlsafe(16)` produces 22 base64 chars from 16 bytes — assert `len(nonce) >= 16`.)

**N2 — charset:** Result contains only URL-safe base64 chars (`[A-Za-z0-9_-]`) and no padding (`=`). CSP nonce values must survive verbatim in a `'nonce-...'` source expression.

**N3 — uniqueness:** Call 100 times; assert all results are distinct. Tests CSPRNG rather than a static value.

**N4 — type:** Returns `str`, not bytes.

### Test class: `TestNeedsRehash`

`needs_rehash` inspects the stored hash prefix to decide whether a re-hash is warranted. Two regime branches exist: argon2 available vs. not. Tests should not depend on which Python packages are installed, so use `unittest.mock.patch` on `transport.security._argon2_available`.

**R1 — argon2 available, argon2 hash → no rehash needed:** Patch `_argon2_available` to return `True`; pass a stored value beginning with `"$argon2"`. Assert `needs_rehash` returns `False`.

**R2 — argon2 available, scrypt hash → rehash needed:** Patch `_argon2_available` to return `True`; pass `"scrypt$32768$8$1$..."`. Assert returns `True`.

**R3 — argon2 available, bcrypt hash → rehash needed:** Patch `_argon2_available` to return `True`; pass `"$2b$..."`. Assert returns `True`.

**R4 — no argon2, scrypt hash → no rehash needed:** Patch `_argon2_available` to return `False`; pass `"scrypt$..."`. Assert returns `False`.

**R5 — no argon2, md5/plain hash → rehash needed:** Patch `_argon2_available` to return `False`; pass `"plaintext"`. Assert returns `True`.

### Test class: `TestOutputEncoding`

Pure string-transformation tests — no mocking required.

**E1 — `encode_html_text` escapes `<`, `>`, `&` but not quotes:** `encode_html_text('<script>&"test"')` → `'&lt;script&gt;&amp;"test"'`. (The `html.escape(quote=False)` contract: quotes are not escaped in text context.)

**E2 — `encode_html_attr` escapes `<`, `>`, `&`, and `"`:** `encode_html_attr('<b onclick="x">y</b>')` — assert `"&quot;"` is present.

**E3 — `encode_url_component` percent-encodes spaces and slashes:** `encode_url_component("hello world/path")` → `"hello%20world%2Fpath"`.

**E4 — `encode_url_component` round-trip:** `urllib.parse.unquote(encode_url_component(value)) == value` for arbitrary strings including Unicode.

**E5 — encode_html_text passthrough for safe input:** ASCII alphanumeric and punctuation that needs no escaping passes through unchanged.

---

## Mock infrastructure notes

- `asyncio.run()` in each async handler test avoids a pytest-asyncio dependency; use `unittest.IsolatedAsyncioTestCase` only if `asyncio.run()` nesting causes issues in the test environment.
- `FakePodmanClient` is already importable from `tests.fakes`; no new fakes are needed.
- The conftest autouse `_block_registry_io` fixture already prevents filesystem I/O — batch tests benefit from this automatically since `_write_batch` calls `_load_registry` / `_save_registry`.
- Patch `transport.lifecycle._write_batch` not `transport.registry._write_batch` — the lifecycle module imports `_write_batch` by name at module load time (lines 76/90), so patching the lifecycle attribute is the correct target.
