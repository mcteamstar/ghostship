# Tasks

## 1. Enforce the guard for wildcard binds

- [ ] 1.1 Update missing-secret bind classification so wildcard binds are guarded when enforcement is enabled while loopback remains exempt; verify existing startup behavior with `pytest tests/unit/test_server.py`.
- [ ] 1.2 Add focused tests for wildcard refuse/warn, loopback allowance, and secret-present startup; verify with `pytest tests/unit/test_server.py`.

## 2. Update operator guidance

- [ ] 2.1 Update `docs/configuration.md` to state that enabled enforcement covers wildcard and specific non-loopback binds while the default remains warn-only; verify the documented behavior matches `transport/bind-guard/spec.md`.
