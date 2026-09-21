## 1. Implement the shared helper

- [x] 1.1 Read `_initiate_login`, `_initiate_claude_login`, and `_initiate_codex_login` in full to understand the exact structure of each PTY read loop before writing the helper
- [x] 1.2 Add `_run_pty_login_flow(pty_sock, prompt_patterns, url_patterns, code_pattern, deadline_secs=45.0)` to `transport/lifecycle.py` — see design.md for the agreed signature
- [x] 1.3 The helper owns: the `select()` loop, chunk accumulation, prompt-answer dispatch, URL/code extraction, background PTY drain thread; returns `(login_url, login_code)` — both may be `None`
- [x] 1.4 Preserve the existing drain pattern: after URL extraction, hand remaining PTY output to a background daemon thread so the event loop is not blocked

## 2. Refactor callers

- [x] 2.1 Refactor `_initiate_login` to call `_run_pty_login_flow` with kiro-cli prompt patterns and URL regexes; retain all container lifecycle logic and state variable updates unchanged
- [x] 2.2 Refactor `_initiate_claude_login` to call `_run_pty_login_flow` with claude prompt patterns and URL regex
- [x] 2.3 Refactor `_initiate_codex_login` to call `_run_pty_login_flow` with codex prompt patterns and URL regex

## 3. Tests and verification

- [x] 3.1 Run `python -m pytest tests/unit/ -x -q` and confirm all existing login tests pass with no behaviour change
- [x] 3.2 Confirm `openspec validate --change trn-178-deduplicate-pty-login-loop` passes
