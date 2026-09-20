## Why

`_initiate_login` (kiro) and `_initiate_claude_login` (claude) in
`transport/lifecycle.py` each contain a near-identical PTY read loop: spawn a login
container, exec a command via `container_exec_pty_stdin`, set the socket non-blocking,
run a `select()` loop for up to 45 seconds reading chunks, answer interactive prompts,
and extract a URL + code from the output. The two loops diverge only in the command
invoked, the prompt patterns answered, and the URL regex. Maintaining them separately
means bug fixes and deadline adjustments must be applied twice. As additional ACP
backends (Codex — TRN-172) add their own login flows the duplication will compound.

## What Changes

- Extract a shared `_run_pty_login_flow` helper in `transport/lifecycle.py` that
  encapsulates the PTY exec, `select()` read loop, prompt-answering, URL/code
  extraction, and background drain, parameterised by: command list, prompt patterns
  (list of `(regex, response)` pairs), URL regex, deadline seconds
- Rewrite `_initiate_login` to call `_run_pty_login_flow` with kiro-cli parameters
- Rewrite `_initiate_claude_login` to call `_run_pty_login_flow` with Claude parameters
- No behaviour change — same timeouts, same prompt responses, same URL patterns

## Capabilities

### New Capabilities
None.

### Modified Capabilities
None — pure refactor. The PTY login flow is an internal implementation detail;
no external API, config, or observable behaviour changes.

## Impact

- `transport/lifecycle.py` — new `_run_pty_login_flow` helper; `_initiate_login` and
  `_initiate_claude_login` become thin wrappers
- `tests/unit/` — existing login tests continue to pass; test coverage of the shared
  helper can replace duplicated test logic
