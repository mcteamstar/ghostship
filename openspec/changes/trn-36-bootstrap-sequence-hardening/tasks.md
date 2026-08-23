## 1. Restructure _finish_crew_setup

- [ ] 1.1 Move `admiral_secret` generation and injection to immediately after `_inject_auth`, before `_patch_crew_config`
- [ ] 1.2 Add `os.fsync(fd)` to the secret injection script before `os.close(fd)`
- [ ] 1.3 Move `_inject_policy` call to after `_seed_openspec_store` (remove it from its current position after the admiral secret block)
- [ ] 1.4 Add a one-line dependency comment above each setup step in `_finish_crew_setup` (e.g. `# depends on: container running (pre-restart)`)
- [ ] 1.5 Verify `admiral_secret` variable is still in scope at the `_inject_policy` call site after the move

## 2. Tests

- [ ] 2.1 Add a test asserting that the mock exec calls for admiral secret injection occur before the mock container restart call in `_finish_crew_setup`
- [ ] 2.2 Add a test asserting the injected secret script contains `os.fsync`

## 3. Validate and verify

- [ ] 3.1 Run `python3 -m unittest discover -s transport -p "test_*.py" -q` — all tests pass
- [ ] 3.2 Run `openspec validate --specs` — no validation errors
- [ ] 3.3 Launch a smoke crew on Academy and confirm `captain(action="order", ...)` on a fresh crew verifies correctly on Raven's first tick
