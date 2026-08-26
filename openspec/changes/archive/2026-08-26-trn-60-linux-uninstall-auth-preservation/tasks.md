## 1. Implementation

- [x] 1.1 In `uninstall.sh`, replace `rm -rf "${HOME}/.local/share/${_MACHINE_NAME}"` with `rm -rf "${HOME}/.local/share/${_MACHINE_NAME}/containers"` in the Linux dedicated machine teardown block (inside `if [[ -z "$KEEP_MACHINE" ]]`)
- [x] 1.2 Update the adjacent comment to explain that only `containers/` is wiped and that `data/` is handled by the data-dir cleanup step below

## 2. Documentation

- [x] 2.1 In `docs/configuration.md` (or the uninstall section of `docs/manual-install.md` if applicable), clarify that on Linux `--purge-auth` controls auth removal independently of `--keep-machine`, and that omitting `--keep-machine` removes only the Podman storage root — not `ga-kiro-auth`
- [x] 2.2 Review the `--purge-auth` and `--keep-machine` flag descriptions in `uninstall.sh`'s usage comment to confirm they accurately describe behaviour after the fix

## 3. Tests

- [x] 3.1 Add or update a test asserting that on Linux, running uninstall without `--purge-auth` and without `--keep-machine` does not remove `ga-kiro-auth`
- [x] 3.2 Add or update a test asserting that `--purge-auth` removes `ga-kiro-auth` regardless of `--keep-machine`

## 4. Validation

- [x] 4.1 Run existing uninstall-related tests to confirm no regressions
- [x] 4.2 Run `openspec validate --change trn-60-linux-uninstall-auth-preservation`
