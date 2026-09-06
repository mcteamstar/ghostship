## 1. HMAC Signing — extend flags to include `force`

- [ ] 1.1 In `transport/files.py`, update `_sign_upload_url()` to accept a `force: bool = False` parameter and include `"force"` in the sorted flags string when `force=True`
- [ ] 1.2 In `transport/files.py`, update the upload path of `_verify_file_token()` to accept a `force: bool = False` parameter and include `"force"` in the reconstructed flags string when `force=True`
- [ ] 1.3 Verify that the flags string in `_sign_upload_url` and `_verify_file_token` (upload path) use identical construction logic (`":".join(sorted(...))`) so signed and verified payloads always match

## 2. Transfer execution — pre-clone removal

- [ ] 2.1 In `transport/files.py`, update `_transfer_upload()` to accept a `force: bool = False` parameter
- [ ] 2.2 In the `if bundle:` branch of `_transfer_upload()`, when `force=True`, run `podman.container_exec_checked(container, ["rm", "-rf", destination])` before the `git clone` call — using list-form to avoid shell interpolation
- [ ] 2.3 Confirm the `rm -rf` call is placed after the `podman.container_archive_put` staging step but before the `git clone` call (stage is already written; only delete destination, not the stage)

## 3. MCP tool — surface `force` parameter

- [ ] 3.1 In `transport/server.py`, add `force: bool = False` to the `supply()` function signature
- [ ] 3.2 Update the `supply()` docstring to document `force`: when `True` with `bundle=True`, removes an existing destination before cloning; default `False` preserves the existing "reject occupied destination" behaviour
- [ ] 3.3 Pass `force` through to `_sign_upload_url(crew_id, clean, unpack=unpack, bundle=bundle, force=force)`
- [ ] 3.4 Include `"force": force` in the `supply()` return dict alongside the existing `"bundle"` and `"unpack"` keys

## 4. Token verification wiring

- [ ] 4.1 In `transport/files.py`, update `_handle_file_put` (the upload HTTP handler) to extract the `force` query parameter from the request and pass it to `_verify_file_token()`
- [ ] 4.2 Pass `force` from the HTTP handler down to `_transfer_upload()` so the pre-clone removal is gated on the originally-signed intent, not an unsigned query param

## 5. Unit tests

- [ ] 5.1 In `tests/unit/test_files.py`, add `class BundleReseedForceTests(unittest.TestCase)` with a test `test_force_reseed_removes_destination_before_clone` — mock `podman.container_exec_checked`, pre-populate a non-empty `destination`, call `_transfer_upload(..., bundle=True, force=True)`, and assert that `rm -rf <destination>` was called before `git clone`
- [ ] 5.2 Add `test_force_false_does_not_rm_destination` — same setup, `force=False`, assert that no `rm -rf` call appears in `exec_calls` before the clone
- [ ] 5.3 Add `test_sign_upload_url_includes_force_in_payload` — call `_sign_upload_url(..., bundle=True, force=True)`, extract `sig`, reconstruct the payload with `force` in flags, verify HMAC matches; call again with `force=False` and confirm the sigs differ
- [ ] 5.4 Add `test_verify_file_token_rejects_force_mismatch` — sign with `force=True`, verify with `force=False`; expect `False` returned; sign with `force=False`, verify with `force=True`; expect `False` returned
- [ ] 5.5 Add `test_supply_returns_force_flag_in_result` — call `server.supply("repo", crew_id="demo", bundle=True, force=True)` with mocked crew/sign helpers; assert `result["force"] is True`

## 6. Verification

- [ ] 6.1 Run `python3 -m py_compile transport/server.py` and `python3 -m py_compile transport/files.py` — confirm both parse cleanly
- [ ] 6.2 Run `python3 -m pytest tests/unit/test_files.py -x -q` — confirm all new and existing file-transfer tests pass
- [ ] 6.3 Run `openspec status --change trn-109-supply-force` and confirm planning is complete (all artifacts green)
