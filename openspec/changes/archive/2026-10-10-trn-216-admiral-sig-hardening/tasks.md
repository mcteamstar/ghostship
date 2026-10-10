## 1. Transport — Signer Update

- [x] 1.1 In `transport/captain.py:_format_captain_mail`, add header-value validation: raise `ValueError` if the derived `subject` or the `sender` string (`admiral@localhost`, hardcoded) contains `\n` or `\r`
- [x] 1.2 Replace the old string-interpolation payload with the canonical length-prefixed encoding: `len(subject_utf8).encode() + b'\n' + subject_utf8 + len(from_utf8).encode() + b'\n' + from_utf8 + body_bytes`, where `body` has already been `rstrip("\r\n")`-ed (existing behaviour is correct on the signer side — preserve it)
- [x] 1.3 Verify `base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")` and `X-Admiral-Sig` header construction are unchanged (no modification needed — confirm by inspection)

## 2. Verifier — Script Update

- [x] 2.1 In `crews/_base/admission/verify-admiral-sig`, add a multipart guard immediately after `msg.get_payload()`: if the result is not a string, `sys.exit(1)` cleanly
- [x] 2.2 Remove the `.rstrip('\n')` call on the body (the body is used verbatim in the new format)
- [x] 2.3 Add header-value validation before payload construction: if `subject` or `sender` contains `\n` or `\r`, `sys.exit(1)`
- [x] 2.4 Replace the old string-interpolation payload with the canonical length-prefixed encoding, mirroring the signer: `f"{len(subject_utf8)}\n".encode() + subject_utf8 + f"{len(from_utf8)}\n".encode() + from_utf8 + body_bytes`
- [x] 2.5 Update the module docstring to document the new payload format

## 3. Unit Tests — Existing Test Update

- [x] 3.1 In `tests/unit/test_admiral_sig.py`, update the `_sign()` helper to use the new length-prefixed payload encoding so existing tests continue to pass against the updated verifier
- [x] 3.2 Update `_make_message()` if any test constructs messages that would trigger the multipart guard (audit: check for any `Content-Type: multipart/*` in test messages — currently none, but confirm)
- [x] 3.3 Verify `WhitespaceBoundaryKeyTests` still passes unchanged (these test key byte handling, not payload format — they should be unaffected)

## 4. Unit Tests — New Test Cases

- [x] 4.1 Add test `test_exit_1_multipart_message`: construct a MIME multipart message with a valid `X-Admiral-Sig` header; assert exit 1 and no unhandled exception (no `AttributeError` in stderr)
- [x] 4.2 Add test `test_exit_1_newline_in_subject`: construct a message with a Subject containing a literal `\n`; assert exit 1
- [x] 4.3 Add test `test_exit_1_newline_in_from`: construct a message with a From value containing a literal `\n`; assert exit 1
- [x] 4.4 Add test `test_exit_0_body_with_trailing_whitespace`: sign a body ending in spaces/tabs; assert exit 0 (verifier does not strip, signer does not strip spaces, round-trip must succeed)
- [x] 4.5 Add test `test_exit_1_old_format_payload`: construct a message signed with the old `Subject:<s>\nFrom:<f>\n\n<body>` payload; assert exit 1 (old-format signatures are rejected by the new verifier)

## 5. Integration Test

- [x] 5.1 Add an integration test (or test class) that calls `_format_captain_mail` with a signing secret, writes the resulting message to a temp file, and pipes it through `verify-admiral-sig`; assert exit 0
- [x] 5.2 Add a variant of 5.1 with a body containing non-ASCII UTF-8 characters; assert exit 0 (tests that length-in-bytes encoding is correct for multi-byte characters)
- [x] 5.3 Add a variant of 5.1 where the body is tampered after signing; assert exit 1

## 6. Verify and Clean Up

- [x] 6.1 Run `python -m pytest tests/unit/test_admiral_sig.py -v` and confirm all tests pass
- [x] 6.2 Run the full test suite (`make test` or equivalent) to confirm no regressions outside the admiral-sig files
- [x] 6.3 Confirm `verify-admiral-sig` is executable (`chmod +x`) — it was already marked executable, but verify after any edit
