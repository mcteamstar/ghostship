## 1. Container Script

- [x] 1.1 Update `inject_auth.py` — change `main()` to accept only `<db_path>` in
  argv (argc == 2, not 3), read `b64_rows` from `sys.stdin.read().strip()`, and update
  the docstring and usage message accordingly

## 2. Lifecycle Caller

- [x] 2.1 Update `_inject_auth` in `transport/lifecycle.py` — replace the
  `container_exec_checked` call with `container_exec_stdin`, passing
  `auth_b64.encode("utf-8")` as `stdin_data` and removing `auth_b64` from the command
  list; update the function docstring to note stdin delivery

## 3. Tests

- [x] 3.1 Add `TestInjectAuthStdin` in `tests/unit/test_lifecycle.py` — assert
  `container_exec_stdin` is used (not `container_exec_checked`), assert `auth_b64` does
  not appear in any argv element, and assert `auth_b64` is present in the
  `stdin_data` bytes; mirror the structure of the existing `TestInjectPolicyStdin` class

## 4. Spec Update

- [x] 4.1 Confirm `openspec validate --strict` passes after committing artifacts
  (proposal.md, specs/secret-delivery-hardening/spec.md, design.md, tasks.md)

## 5. Verification

- [x] 5.1 Run `python -m pytest tests/unit/test_lifecycle.py -k TestInjectAuthStdin -v`
  and confirm all new assertions pass
- [x] 5.2 Run the full unit test suite (`python -m pytest tests/unit/`) and confirm no
  regressions
