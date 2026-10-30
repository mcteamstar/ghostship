# TRN-292 Tasks — Test Coverage: Batch Dispatch/Pickup, File Transfer Handlers, Security Primitives

All tasks are test-only. No production code is modified.

## T1 — `TestBatchDispatch`: batch dispatch scenarios

File: `tests/unit/test_lifecycle.py` (or `tests/unit/test_batch.py` if test_lifecycle.py exceeds ~1 500 lines)

Patch targets (all at `transport.lifecycle.*`): `_require_crew`, `_ensure_crew_running`, `_resolve_dispatch_slot`, `_crew_api_with_recovery`, `_write_batch`.

- [ ] T1.1 D1 — successful full batch: 2 tasks dispatched, status="dispatched", task_ids correct, `_write_batch` called with status="pending"
- [ ] T1.2 D2 — partial batch mid-dispatch: second spawn raises `CrewUnresponsiveError`, status="partial", error surfaced, `_write_batch` called with status="partial"
- [ ] T1.3 D3 — spawn returns no task id: `_crew_api_with_recovery` returns `{}`, status="partial", error mentions "no task id"
- [ ] T1.4 D4 — batch too small (1 task): error mentions "at least 2"
- [ ] T1.5 D5 — batch too large: `GA_BATCH_MAX_TASKS=2` env override, 3 tasks, error mentions "exceeds maximum" (restore env in tearDown)
- [ ] T1.6 D6 — crew not found: `_require_crew` raises `ValueError`, error is non-empty

## T2 — `TestBatchPickup`: pickup state machine and edge cases

File: same as T1.

Injected callables: `pickup_single`, `read_all_mail_counts`, `update_batch_status` (all `MagicMock` or small lambdas). Patch `time.monotonic` and `time.sleep` for timeout/interval scenarios.

- [ ] T2.1 P1 — all done on first poll: both tasks done, result["done"] True, `update_batch_status` called with "complete"
- [ ] T2.2 P2 — snapshot mode (timeout=0): one done, one pending, returns immediately, result["done"] False
- [ ] T2.3 P3 — wall-time timeout: timeout=3, never all done, result["reason"]=="timeout"; use patched monotonic to avoid real sleep
- [ ] T2.4 P4 — admiral-mail early return: `read_all_mail_counts` count rises on second call, result["reason"]=="admiral_mail"
- [ ] T2.5 P5 — lost task_id normalisation: `pickup_single` returns 404-shaped error, result[task_id]["lost"] True
- [ ] T2.6 P6 — empty task list: task_ids=[], result["total_tasks"]==0, result["done"] False

## T3 — `TestFileGetHandler` and `TestFilePutHandler`

File: `tests/unit/test_files.py` (append after existing `TestSignVerifyRoundTrip`).

Fake request: minimal stub with `.path_params`, `.query_params`, async `.body()`. Patch targets at `transport.files.*`: `_verify_file_token`, `_lifecycle._require_crew`, `_lifecycle._ensure_crew_running`, `_lifecycle._to_crew`, `_get_podman`, `_transfer_upload`. Use `asyncio.run()` to invoke async handlers.

GET handler (`_handle_file_get`):
- [ ] T3.1 FG1 — expired token → 403
- [ ] T3.2 FG2 — invalid crew_id format → 400
- [ ] T3.3 FG3 — missing crew (KeyError from `_require_crew`) → 404
- [ ] T3.4 FG4 — running crew, plain file → 200
- [ ] T3.5 FG5 — stopped crew, archive API path → 200 (not 404)

PUT handler (`_handle_file_put`):
- [ ] T3.6 FP1 — expired token → 403
- [ ] T3.7 FP2 — invalid crew_id → 400
- [ ] T3.8 FP3 — empty body → 400
- [ ] T3.9 FP4 — successful plain upload → 200
- [ ] T3.10 FP5 — `_transfer_upload` raises → 500

## T4 — `TestCspNonce`, `TestNeedsRehash`, `TestOutputEncoding`

File: `tests/unit/test_security.py` (append after existing `TestSecretRedactionFilter`).

No new dependencies — all functions are pure or mock-controlled via `unittest.mock.patch`.

CSP nonce (`TestCspNonce`):
- [ ] T4.1 N1 — length ≥ 16 chars
- [ ] T4.2 N2 — charset is URL-safe base64 only (`[A-Za-z0-9_-]`, no `=`)
- [ ] T4.3 N3 — uniqueness: 100 calls, all distinct
- [ ] T4.4 N4 — return type is `str`

needs_rehash (`TestNeedsRehash`), patch `transport.security._argon2_available`:
- [ ] T4.5 R1 — argon2 available + argon2 stored → False (no rehash)
- [ ] T4.6 R2 — argon2 available + scrypt stored → True
- [ ] T4.7 R3 — argon2 available + bcrypt stored → True
- [ ] T4.8 R4 — no argon2 + scrypt stored → False
- [ ] T4.9 R5 — no argon2 + plaintext stored → True

Output encoding (`TestOutputEncoding`):
- [ ] T4.10 E1 — `encode_html_text` escapes `<>&` but not quotes
- [ ] T4.11 E2 — `encode_html_attr` escapes `<>&"` (produces `&quot;`)
- [ ] T4.12 E3 — `encode_url_component` encodes spaces as `%20`, slashes as `%2F`
- [ ] T4.13 E4 — `encode_url_component` round-trips via `urllib.parse.unquote`
- [ ] T4.14 E5 — `encode_html_text` passes safe ASCII through unchanged

## T5 — Full unit suite green

- [ ] T5.1 Run `pytest tests/unit/ -q` from repo root and confirm zero failures and zero errors
- [ ] T5.2 Confirm no existing tests were broken by the new test classes (check for import-time side effects from `GA_FILE_SECRET` / `GA_BATCH_MAX_TASKS` env mutations — use `addCleanup` or `tearDown` to restore)
