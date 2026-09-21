## Context

See proposal.md — Why.

Three PTY login loops exist in `transport/lifecycle.py`:
- `_initiate_login` (~L2226–2439) — kiro-cli device flow
- `_initiate_claude_login` (~L2440–2637) — claude auth login
- `_initiate_codex_login` (~L2809–end) — codex login

Each loop: spawns a login container, calls `container_exec_pty_stdin`, sets the socket
non-blocking, runs a `select()` loop for up to 45 seconds, answers interactive prompts,
extracts a URL and optional code, drains the PTY in a background thread.

The loops differ in:
1. Command list (`kiro-cli login --use-device-flow` / `claude auth login` / `codex login`)
2. Interactive prompt patterns (kiro has Start URL + Region prompts; claude/codex have simpler Y/N prompts)
3. URL regex (kiro matches multiple patterns; claude/codex match `https?://\S+`)
4. State variables and locks (`_login_pending` / `_claude_login_pending` / `_codex_login_pending`)
5. Container nuke function called on failure

## Goals / Non-Goals

**Goals**
- Extract a `_run_pty_login_flow` helper that owns the shared PTY read loop
- Reduce three copies of the select/recv/decode/prompt-answer loop to one
- No behaviour change — identical timeouts, prompt responses, URL patterns

**Non-Goals**
- Merging the container start/stop/state-machine logic (stays per-backend)
- Changing the login API endpoints or their response shapes
- Supporting new backends (Codex already landed in TRN-172)

## Decisions

**Helper signature:**
```python
def _run_pty_login_flow(
    pty_sock: socket.socket,
    prompt_patterns: list[tuple[re.Pattern, bytes]],
    url_patterns: list[re.Pattern],
    code_pattern: re.Pattern | None,
    deadline_secs: float = 45.0,
) -> tuple[str | None, str | None]:
    """Returns (login_url, login_code). Both may be None on timeout."""
```
The caller handles container lifecycle (start/nuke) and state variables. The helper
owns only the `select()` loop and output parsing. This keeps the callers' error
handling paths unchanged and avoids introducing new abstraction over the state machine.

**Caller structure stays the same.**
`_initiate_login`, `_initiate_claude_login`, and `_initiate_codex_login` remain as
thin wrappers that: start the container → call `_run_pty_login_flow` → check result →
update state → return response dict. No merge of the three functions.

**Background PTY drain stays in the helper.**
The drain thread is always needed after URL extraction. Moving it into the helper
avoids another point of divergence.

## Risks / Trade-offs

[Risk] The helper's abstraction leaks if a future backend needs a fundamentally
different loop structure (e.g. binary protocol) → Mitigation: The helper is
internal; callers can bypass it if needed without API changes.

[Risk] Subtle behavioural difference between the three loops not caught during
extraction → Mitigation: Existing login tests cover each backend; run full unit
suite after refactor.

## Migration Plan

Pure refactor — no deployment steps beyond normal code change. Tests must stay
green before merging.
