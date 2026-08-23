## 1. HMAC token length (Finding 1)

- [ ] 1.1 In `_sign_file_url` (server.py ~line 4382), change `.hexdigest()[:16]` to `.hexdigest()[:32]`
- [ ] 1.2 In `_sign_upload_url` (server.py ~line 4827), change `.hexdigest()[:16]` to `.hexdigest()[:32]`
- [ ] 1.3 In `_verify_file_token` (server.py ~line 4408), change `.hexdigest()[:16]` to `.hexdigest()[:32]` in the `expected` computation

## 2. Upload mode in HMAC signature (Finding 2)

- [ ] 2.1 Update `_sign_upload_url(crew_id, path)` signature to `_sign_upload_url(crew_id, path, unpack=False, bundle=False)` and encode mode as `"unpack"` / `"bundle"` / `""` in the payload field: `f"{crew_id}:{path}::{mode}:{expires}"`
- [ ] 2.2 Remove the existing comment in `_sign_upload_url` that justifies leaving mode outside the signed payload (design D2 supersedes it)
- [ ] 2.3 Update `_verify_file_token` to accept `mode: str = ""` and include it identically in its payload reconstruction
- [ ] 2.4 In `_handle_file_put`, extract `unpack`/`bundle` from query params *before* calling `_verify_file_token` and derive `mode`; pass `mode` to `_verify_file_token`
- [ ] 2.5 In `supply()` (server.py ~line 2890), pass `unpack=unpack, bundle=bundle` to `_sign_upload_url`

## 3. Admiral secret not in admission_policy.json (Finding 3)

- [ ] 3.1 In `_inject_policy` (server.py ~line 2686), remove the `admiral_secret` field from the `admission_policy.json` content that gets written into the crew container — the secret is already written to `.admiral_secret` file (line 2789-2792) which `verify-admiral-sig` reads; the policy JSON copy is the exposure
- [ ] 3.2 Update the docstring / inline comment for `_inject_policy` to note that `admiral_secret` is delivered via `.admiral_secret` file (0600) and is not stored in `admission_policy.json`
- [ ] 3.3 Update `docs/auth.md` to document the threat model: why the secret lives in `.admiral_secret` file (0600, not agent-readable) rather than in a policy JSON that any agent can `cat`
- [ ] 3.4 Verify (add a test assertion) that `_inject_policy` output does not contain `admiral_secret` as a JSON key

## 4. Default HOST binding (Finding 4)

- [ ] 4.1 Change line 84 in `server.py` from `os.environ.get("HOST", "0.0.0.0")` to `os.environ.get("HOST", "127.0.0.1")`
- [ ] 4.2 Update `docs/configuration.md` to document the new default (`127.0.0.1`) and how to opt in to LAN exposure (`HOST=0.0.0.0`)

## 5. crew_id format validation in file handlers (Finding 5)

- [ ] 5.1 Extract the `crew_id` regex (`^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$`) into a module-level `CREW_ID_RE` constant (or reuse the existing pattern from `launch()`)
- [ ] 5.2 In `_handle_file_get`, add `re.fullmatch(CREW_ID_RE, crew_id)` guard immediately after extracting `crew_id` from path params; return 400 on mismatch
- [ ] 5.3 In `_handle_file_put`, add the same guard in the same position

## 6. Reject empty path in evac (Finding 6)

- [ ] 6.1 In `evac()` (server.py ~line 2953), add a guard after `clean = path.lstrip("/")`: if `not clean`, return `{"error": "path must not be empty"}`

## 7. dangerously_skip_permissions annotation (Finding 8)

- [ ] 7.1 Add an inline comment at the `dangerously_skip_permissions=True` call site (~line 2667) explaining: (a) why the bypass is needed (gateway process inside the crew container runs as a different UID than the transport, so normal permission enforcement would block the config write), and (b) the security implication (flag bypasses KiroCrew's permission guard for this specific operation only)

## 8. crews.json file permissions (Finding 9)

- [ ] 8.1 In `_save_registry` (server.py ~line 877), add `os.chmod(REGISTRY_PATH, 0o600)` immediately after `os.replace(tmp, REGISTRY_PATH)`

## 9. Tests

- [ ] 9.1 Add tests for 128-bit HMAC: assert `len(sig) == 32` in generated URLs; assert a 16-char sig is rejected by `_verify_file_token`
- [ ] 9.2 Add tests for upload mode signing: assert a token signed with `mode=""` fails verification when `mode="unpack"` is presented, and vice versa
- [ ] 9.3 Add test: `_handle_file_put` rejects a request whose token was signed with `bundle=False` but arrives with `&bundle=1`
- [ ] 9.4 Add test: `evac(path="", crew_id=...)` returns `{"error": "path must not be empty"}`
- [ ] 9.5 Add test: `_handle_file_get` returns 400 for a `crew_id` containing `/`, `..`, `%`, or uppercase characters
- [ ] 9.6 Add test: `_handle_file_put` returns 400 for the same malformed `crew_id` cases
- [ ] 9.7 Add test: `_save_registry` produces a file with permissions `0o600`
- [ ] 9.8 Add test: `_inject_policy` output JSON does not contain an `admiral_secret` key

## 10. Documentation

- [ ] 10.1 Update `docs/configuration.md` entry for `HOST` to reflect new default (`127.0.0.1`) and document opt-in to `0.0.0.0`
- [ ] 10.2 Update `docs/auth.md` security section to describe admiral secret delivery path (`.admiral_secret` file, 0600 permissions, not in `admission_policy.json`) and the threat model it addresses
