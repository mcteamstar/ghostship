## 1. Harden maildeliver

- [ ] 1.1 In `crews/_base/admission/maildeliver`, after deriving `BASE` and before `mkdir -p`, insert validation that rejects the recipient unless the derived base matches `^[a-z][a-z0-9_-]*$` (non-empty; no `/`, `..`, leading `.`, or NUL byte)
- [ ] 1.2 On a rejected base, write a diagnostic naming the offending recipient to stderr and `exit` non-zero before any filesystem operation
- [ ] 1.3 Add the defense-in-depth confinement check: after building `MAILDIR="/var/mail/${BASE}"`, confirm its parent resolves to `/var/mail` (e.g. `[ "$(dirname "$MAILDIR")" = /var/mail ]`) and exit non-zero with a diagnostic otherwise
- [ ] 1.4 Confirm legitimate behavior is unchanged: `@domain` and `+extension` stripping, and the Maildir `tmp/` → `new/` atomic rename, still run for a valid base

## 2. Tests

- [ ] 2.1 Add a shell test that `maildeliver` delivers a message to `/var/mail/spectre/new/` for recipient `spectre+6bf99101@localhost` (instance form) and `/var/mail/captain/new/` for `captain@localhost` (generic form)
- [ ] 2.2 Add tests asserting `maildeliver '../../etc/cron.d/evil@localhost'` and `maildeliver '/root/.ssh/authorized_keys@localhost'` exit non-zero and create no file or directory outside `/var/mail/`
- [ ] 2.3 Add tests asserting empty (`@localhost`), dotfile (`.@localhost`), and parent (`..@localhost`) bases exit non-zero and write nothing
- [ ] 2.4 Run the test suite against all eight persona names (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, `admiral`) to confirm none is rejected

## 3. Validate

- [ ] 3.1 Run `openspec validate --store repo --change trn-217-maildeliver-path-traversal --strict` and resolve any findings
- [ ] 3.2 Verify no caller in `academy/skills/ghostship-mail/SKILL.md` or `academy/steering/STANDING_ORDERS.md` relies on a non-persona recipient (expected: none; no change needed)
