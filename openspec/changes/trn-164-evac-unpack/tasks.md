## 1. HMAC / token signing

- [ ] 1.1 Update `_sign_file_url` in `transport/files.py` to accept `unpack: bool = False` and include `unpack` in the sorted `flags` set alongside `bundle`
- [ ] 1.2 Update `_verify_file_token` GET path in `transport/files.py` to reconstruct `flags` including `unpack` (read `?unpack=` query param in `_handle_file_get` before calling `_verify_file_token`)
- [ ] 1.3 Verify HMAC round-trip: a token signed with `unpack=False` is rejected when `unpack=True` is present on the request, and vice versa

## 2. HTTP handler — running-crew path

- [ ] 2.1 Parse `unpack = request.query_params.get("unpack", "0") in ("1", "true", "yes")` at the top of `_handle_file_get`, alongside the existing `bundle` parse
- [ ] 2.2 Add mutual-exclusion guard: if `unpack` and `bundle` are both set, return 400 Bad Request
- [ ] 2.3 Add `unpack` branch in the running-crew section: when `unpack=True`, call `podman.container_archive_get(crew["container"], f"{ws}/{clean}")` and return a `StreamingResponse` with `media_type="application/x-tar"` (bypass `_TarMemberStream`)

## 3. HTTP handler — stopped-crew path

- [ ] 3.1 Add `unpack` branch in the stopped-crew section of `_handle_file_get`: when `unpack=True`, call `podman.container_archive_get(crew["container"], f"{ws}/{clean}")` directly (same Podman archive-GET path used for plain files today) and return a `StreamingResponse` with `media_type="application/x-tar"`

## 4. MCP tool

- [ ] 4.1 Add `unpack: bool = False` parameter to `evac()` in `transport/server.py`
- [ ] 4.2 Add mutual-exclusion guard in `evac()`: if `unpack=True` and `bundle=True`, return `{"error": "unpack and bundle cannot both be True"}`
- [ ] 4.3 Pass `unpack` to `_sign_file_url` and append `&unpack=1` to the URL when `unpack=True`
- [ ] 4.4 Update `evac()` docstring: document the new `unpack` parameter, the `unpack`/`bundle` mutual exclusion, and add a curl example for directory extraction (`curl -s "<url>" -o ./output.tar`)
- [ ] 4.5 Add `"unpack": unpack` to the `evac()` result dict

## 5. Tests

- [ ] 5.1 `test_file_transfer.py`: test that `_sign_file_url(unpack=True)` includes `unpack` in the flags and that the resulting token is rejected when `unpack` is toggled on the request
- [ ] 5.2 `test_file_transfer.py`: test `_verify_file_token` GET path rejects mismatched `unpack` flag (signed False, presented True, and vice versa)
- [ ] 5.3 `test_file_transfer.py` or `test_server.py`: test `_handle_file_get` with `unpack=True` — mock `container_archive_get` and verify the raw stream is returned with `application/x-tar` content type
- [ ] 5.4 `test_file_transfer.py` or `test_server.py`: test `_handle_file_get` with both `unpack=True` and `bundle=True` — verify 400 response
- [ ] 5.5 `test_server.py`: test `evac()` MCP tool with `unpack=True` — verify returned dict includes `"unpack": True` and URL contains `&unpack=1`
- [ ] 5.6 `test_server.py`: test `evac(unpack=True, bundle=True)` — verify error returned without presigning
