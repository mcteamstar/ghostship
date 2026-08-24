## 1. Builder ID login menu fix

- [x] 1.1 Reproduce the hang locally: run `POST /login` against a transport with no `KIRO_IDENTITY_PROVIDER` set and capture the raw PTY output, confirming the `Select login method` menu text and its exact wording/highlight for the current kiro-cli version
- [x] 1.2 Refactor `_handle_login_post`'s prompt-answering loop (`transport/server.py`) from the two hardcoded `if` blocks into an ordered list of (matcher, answer) rules, preserving existing `Start URL`/`Region` behavior exactly, and verify existing login tests in `transport/test_transport.py` still pass unmodified
- [x] 1.3 Add a rule that detects `Select login method` and sends a bare `\n` to accept the highlighted Builder ID default, only when no `Start URL` prompt has been seen yet in this session, and verify a live `POST /login` with no identity provider configured returns `status: "pending"` with a `login_url` and `code` instead of a 500
- [x] 1.4 Add a PTY transcript fixture test in `transport/test_transport.py` reproducing the captured menu output from 1.1, asserting `_handle_login_post` answers it and extracts a device URL, and verify it fails against the pre-fix code (confirms it's a real regression test)

## 2. Verification

- [x] 2.1 Run the full `transport/` test suite and verify all tests pass, including the new fixture from 1.4
- [x] 2.2 Manually re-run the sequence that originally surfaced the bug — vanilla `./install.sh` with no identity provider configured, `POST /login`, complete the Builder ID device flow in a browser — and verify `GET /login` reports `complete` without any manual workaround
  > Verified externally by Admiral against commit 7e0fc5d: transport image built with no KIRO_IDENTITY_PROVIDER, POST /login returned Builder ID device URL, browser flow completed, GET /login → {"status":"complete"}. Select login method menu handled correctly.
- [x] 2.3 Also manually re-verify the IAM Identity Center path (`KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` configured) still works end-to-end after the refactor in 1.2, since it must not regress
  > Verified externally by Admiral against commit 7e0fc5d: KIRO_IDENTITY_PROVIDER/KIRO_REGION/KIRO_LICENSE set to a real IAM Identity Center org. POST /login returned IDC device URL, browser flow completed, GET /login → {"status":"complete"}. No IDC regression.
