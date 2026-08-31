# Implementation Tasks

## 1. Shared proxy sanitisation

- [x] 1.1 Add `_sanitise_query_string(raw: bytes) -> str` in `transport/server.py`, decoding with `latin-1` and stripping exactly `0x00`–`0x1F` and `0x7F` control characters via `re.sub`.
- [x] 1.2 Use `_sanitise_query_string` in both `_handle_crew_ui_proxy` and `_handle_crew_api_proxy`.

## 2. Verification and handoff

- [ ] 2.1 Add `TestProxyQuerySanitisation` coverage in `tests/unit/test_server.py` for CR/LF/NUL stripping in both proxy paths and unchanged ordinary and percent-encoded query strings.
- [ ] 2.2 Run the targeted proxy tests and the existing test suite to confirm nothing else broke.
- [ ] 2.3 Review the focused implementation diff against `specs/proxy-hosting/spec.md` and `design.md`, then mark completed implementation and verification tasks.
- [ ] 2.4 Commit the production and test implementation as a separate change from this planning-artifact handoff.
