# Design

## Context

See proposal.md — Why. Four independent findings; each fix is self-contained.

The inject_policy pattern to follow is the admiral-secret delivery in TRN-211:
`lifecycle.py` calls `container_exec_stdin(podman, crew_id, cmd, input=secret)`.
`inject_policy.py` already reads its positional args; after this change it reads
the key from `sys.stdin.read().strip()` instead of `sys.argv[1]`.

`hmac.new()` is a thin alias for `hmac.HMAC()` with identical signature — no
behaviour change, just deprecation suppression.

The port range default is a copy-paste error from when the range was larger.
The YAML default (`portal.dashboard.port_range.size`) and docs both say `64`.

The deleted tests require reading the relevant specs and re-authoring the test
modules from scratch since no prior source exists in git.

## Goals / Non-Goals

**Goals:** Pass all existing tests. Add the six missing test modules. Fix the
argv key exposure. Remove deprecated hmac usage. Correct the default.

**Non-Goals:** Refactoring `inject_policy.py` beyond the stdin switch.
Expanding test coverage beyond what the six modules' specs mandate.

## Decisions

**H-1 — stdin delivery pattern**

Use `container_exec_stdin` (already exists, used by admiral-secret delivery).
Pass the HMAC key as the `input` kwarg. `inject_policy.py` switches from
`sys.argv[1]` to `sys.stdin.read().strip()`. The `--key` argv slot is removed;
passing it would defeat the fix. No other callers exist.

Alternative considered: environment variable. Rejected — env vars are also
visible in `/proc/<pid>/environ` to processes with the same UID on Linux.

**C-1 — test authoring**

Each module is authored against its parent spec requirement(s). The
`transport-test-coverage` spec lists the behaviours each module must cover.
Tests use the existing `tests/unit/` fixture patterns (mock podman, `TestCase`
subclasses). No new test infrastructure needed.

## Risks / Trade-offs

- `inject_policy.py` stdin read blocks until EOF. `container_exec_stdin` closes
  the write end after sending — this is already the pattern for admiral-secret
  delivery, so no new risk.
- The six test modules will be partial coverage of their specs (they test the
  headline behaviours, not every edge case). Full coverage is a separate effort.

## Migration Plan

All changes land in `release/0.8.0` as sequential commits. No deploy steps
beyond `ghostship upgrade` on the live install. No migration needed.

## Open Questions

None.
