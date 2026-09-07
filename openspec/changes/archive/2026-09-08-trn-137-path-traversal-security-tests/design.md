## Context

See proposal.md. Four security-critical functions have zero test coverage; one (`_safe_workspace_path`) has an active path traversal bug. The dead-code colon check in `_validate_next_url` adds noise without protection.

## Goals / Non-Goals

**Goals:**
- Fix the adjacent-directory path traversal in `_safe_workspace_path()`
- Remove dead colon check in `_validate_next_url()`
- Add direct unit tests for `_safe_workspace_path`, `_validate_next_url`, `_parse_bearer_token`, `_validate_ref`

**Non-Goals:**
- Refactoring the functions themselves beyond the one-line fix
- Adding e2e tests

## Decisions

**D1: One-character fix — append `/` to root in prefix check**
`str(resolved).startswith(str(root) + "/")` is the correct fix. Alternatively compare `resolved.parts[:len(root.parts)] == root.parts` — both correct, prefer the simpler string approach as it matches the existing code style.

**D2: Dead colon check removal**
`":" in url.split("/")[0]` always evaluates to `False` on any path starting with `/` because `split("/")[0]` yields `""`. Removing it is safe — the `startswith("/") and not startswith("//")` guard above it already blocks `javascript:` and `//evil.com` inputs.

**D3: Tests in existing test files where functions are already tested, new file for auth.py**
`_safe_workspace_path` → `tests/unit/test_files.py` (new or extend existing). `_validate_next_url` → `tests/unit/test_server.py`. `_parse_bearer_token` → `tests/unit/test_auth.py`. `_validate_ref` → `tests/unit/test_files.py` or `test_server.py` (wherever evac tests live).

## Risks / Trade-offs

- [Risk] Changing the prefix check could theoretically break a path that previously passed — but any path that was passing via the adjacent-directory loophole was already a bug, not legitimate behaviour.

## Migration Plan

No migration needed. One-line code fixes + new tests. No behaviour change for valid paths.

## Open Questions

None.
