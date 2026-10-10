## ADDED Requirements

### Requirement: maildeliver confines delivery to known-persona mailboxes under /var/mail

The local delivery boundary (`maildeliver`) SHALL validate the mailbox name derived from a recipient address and SHALL confine every delivery to a direct child directory of `/var/mail/`, before performing any filesystem operation (`mkdir`, write, or rename). A recipient whose derived mailbox name is not a safe, flat name SHALL be rejected with a non-zero exit status and a diagnostic on stderr, and no file SHALL be created anywhere.

The derived mailbox name is the recipient local-part after stripping the `@domain` suffix and the `+extension` plus-address segment (the existing behavior). `maildeliver` SHALL additionally require that this derived name:

- is non-empty;
- matches the character class `^[a-z][a-z0-9_-]*$` — a lowercase letter followed by lowercase letters, digits, underscores, or hyphens only;
- contains no path separator (`/`), no parent-directory segment (`..`), no leading `.`, and no NUL byte.

As defense in depth, after constructing the target path `maildeliver` SHALL confirm the resulting mailbox directory is a direct child of `/var/mail/` (its parent resolves to `/var/mail`) and SHALL refuse delivery otherwise, so no interpolation can escape `/var/mail/` even if the name check is bypassed.

This validation SHALL NOT alter delivery for any legitimate recipient: all known persona mailboxes — `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, `admiral`, in both the generic (`<persona>@localhost`) and instance (`<persona>+<task_id>@localhost`) forms — SHALL continue to deliver atomically via the existing Maildir `tmp/` → `new/` rename.

#### Scenario: Legitimate persona recipient delivers unchanged

- **WHEN** `maildeliver spectre+6bf99101@localhost` is invoked with a message on stdin
- **THEN** the message is delivered atomically to `/var/mail/spectre/new/` via the Maildir `tmp/` → `new/` rename, exactly as before — the plus-extension is stripped and the base `spectre` passes validation

#### Scenario: Generic persona recipient delivers unchanged

- **WHEN** `maildeliver captain@localhost` is invoked
- **THEN** the message is delivered to `/var/mail/captain/new/`, the derived base `captain` having passed validation

#### Scenario: Relative path-traversal recipient is rejected

- **WHEN** `maildeliver '../../etc/cron.d/evil@localhost'` is invoked
- **THEN** `maildeliver` exits non-zero, writes a diagnostic to stderr, and creates no directory or file under `/etc/` or anywhere outside `/var/mail/` — the derived base contains `/` and `..` and fails validation before any `mkdir`

#### Scenario: Absolute-path recipient is rejected

- **WHEN** `maildeliver '/root/.ssh/authorized_keys@localhost'` is invoked
- **THEN** `maildeliver` exits non-zero with a stderr diagnostic and writes nothing — the derived base begins with `/` and fails validation, and the parent-of-target confinement check would independently refuse it

#### Scenario: Empty or dotfile base is rejected

- **WHEN** `maildeliver '@localhost'` or `maildeliver '.@localhost'` or `maildeliver '..@localhost'` is invoked
- **THEN** `maildeliver` exits non-zero with a stderr diagnostic and writes nothing — an empty base, a leading-dot base, and a `..` base all fail validation

#### Scenario: Delivery is pinned to a direct child of /var/mail

- **WHEN** any recipient passes the name check and `maildeliver` constructs the target mailbox path
- **THEN** delivery proceeds only if the mailbox directory's parent resolves to `/var/mail`; otherwise `maildeliver` exits non-zero and writes nothing
