## 1. Fix maildeliver

- [ ] 1.1 Add BASE validation in `crews/_base/admission/maildeliver` immediately after `BASE="${LOCAL%%+*}"`: reject inputs not matching `^[a-z][a-z0-9_-]*$` with a stderr message and `exit 1`

## 2. Fix sendmail-local

- [ ] 2.1 Add the same `^[a-z][a-z0-9_-]*$` BASE validation in `crews/_base/admission/sendmail-local` for each recipient before invoking `maildeliver`, with a stderr message and `exit 1` on failure

## 3. Tests

- [ ] 3.1 Create `tests/unit/test_maildeliver.sh`: a shell test script that stubs out `mkdir`, `cat`, and `mv` (or uses a temp dir) and verifies `maildeliver` exits 0 for valid addresses (`ghost@localhost`, `ghost+abc@localhost`, `raven@localhost`) and exits 1 for invalid ones (`../../tmp/x@localhost`, `../etc/passwd@localhost`, `@localhost`, `Ghost@localhost`, `ghost @localhost`)
- [ ] 3.2 Verify `sendmail-local` also rejects path traversal addresses (can be a brief addendum in the same test file or a separate function)
- [ ] 3.3 Ensure the test file is executable and noted in `tests/unit/README.md` (if one exists) or `tests/run.sh`
