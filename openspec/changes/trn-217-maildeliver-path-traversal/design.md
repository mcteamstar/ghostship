## Context

See `proposal.md` — Why. `crews/_base/admission/maildeliver` is a short `set -euo pipefail` bash script baked into the crew image and invoked by the local MTA (msmtp-mta) for every local delivery. It derives a mailbox base from the recipient (`BASE="${LOCAL%%+*}"`, `LOCAL="${RECIPIENT%%@*}"`) and uses it unvalidated in `MAILDIR="/var/mail/${BASE}"`, then `mkdir -p "${MAILDIR}/..."`, `cat > tmp`, `mv tmp new`. The recipient is attacker-influenceable: any dispatched agent calls `maildeliver <to>` directly (see the `ghostship-mail` skill), and inbound messages carry a recipient the MTA passes through.

Constraints: the fix must be pure bash using image builtins (no new dependency), must not change delivery for any legitimate persona recipient, and must fail closed — reject before any `mkdir`/write so a rejected recipient leaves no trace on disk.

## Goals / Non-Goals

**Goals:**
- Guarantee every successful delivery lands in a direct child of `/var/mail/` and nowhere else.
- Reject path-traversal (`..`, `/`), absolute-path, dotfile, empty, and NUL-byte recipients with a non-zero exit and a stderr diagnostic, before touching the filesystem.
- Preserve existing `@domain` and `+extension` stripping and Maildir atomic-rename semantics for all valid persona recipients.

**Non-Goals:**
- Enforcing a closed allowlist of the exact eight persona names in the script. The character-class check plus the `/var/mail` confinement check already prevent escape; a hardcoded name list would couple the delivery script to the persona roster and break silently when a new persona is added. (See Decisions.)
- Authenticating senders, signing, or any change to mail content, headers, or threading — out of scope for this security fix.
- Changing how agents send mail or the `ghostship-mail` skill.

## Decisions

**D1 — Character-class allowlist over blocklist, over hardcoded persona list.**
Validate the derived base against `^[a-z][a-z0-9_-]*$`. A positive character class is inherently traversal-proof: it admits no `/`, no `.`, no `..`, no NUL, no leading dot, and no empty string, so one anchored test replaces several blocklist patterns and cannot be bypassed by an encoding a blocklist missed. Chosen over (a) a blocklist of dangerous sequences — brittle, easy to under-specify — and (b) a hardcoded `ghost|spectre|...` list — correct today but couples delivery to the roster and fails closed-but-wrong when personas change. The class matches every current and foreseeable persona mailbox name while rejecting everything dangerous.

**D2 — Defense-in-depth path confinement.**
After building `MAILDIR="/var/mail/${BASE}"`, independently confirm its parent directory resolves to `/var/mail` before any write (e.g. compare `"$(dirname "$MAILDIR")"` to `/var/mail`, or resolve and prefix-check). This is redundant with D1 by design: two independent controls mean a defect in either one alone cannot produce an out-of-tree write. Kept cheap — no external process beyond shell builtins / a single `dirname`.

**D3 — Fail closed, before any filesystem op.**
All validation runs immediately after deriving `BASE`, before the `mkdir -p`. On rejection: `echo` a diagnostic naming the offending recipient to stderr and `exit` non-zero (distinct from the usage error's exit 1 is acceptable but not required). Because `set -e` is active and nothing is written before the check, a rejected delivery leaves the filesystem untouched.

**D4 — Validate the stripped base, not the raw recipient.**
Keep the existing strip order (`@` then `+`) and validate the result, so legitimate instance addresses like `ghost+../x@localhost` are judged on the base (`ghost`) for the persona but the extension is discarded — the extension never reaches a path, so only the base needs validating. The raw recipient is still safe because the base is the only part interpolated into a path.

## Risks / Trade-offs

- **[A future persona name violates `^[a-z][a-z0-9_-]*$`]** → The class already covers lowercase names with digits/`_`/`-`; a name needing other characters is unlikely and would itself be a questionable mailbox name. Mitigation: documented class; widening it is a one-line, reviewable change.
- **[`dirname`/resolution behaves differently if `/var/mail` is a symlink]** → Mitigation: `/var/mail` is a fixed image path; the confinement check compares against the literal `/var/mail`. If it must follow symlinks later, use `realpath -m` on both sides — noted but not needed now.
- **[Over-strict rejection breaks a legitimate delivery]** → Mitigation: the six spec scenarios assert both acceptance (generic + instance persona forms) and rejection paths; verify against all eight persona names before shipping.
- **[Behavioral change for callers relying on the old permissive behavior]** → No legitimate caller sends a traversal recipient; the `ghostship-mail` skill and `STANDING_ORDERS.md` only ever use valid persona addresses. Rejection of a malicious recipient is the intended change.

## Migration Plan

1. Edit `crews/_base/admission/maildeliver` to insert the validation + confinement block between `BASE` derivation and `mkdir -p`.
2. Add a small test (shell-based) exercising the spec scenarios: valid generic/instance delivery succeeds; `../`, absolute, empty, and dotfile recipients exit non-zero and write nothing.
3. The script ships in the crew image; the fix takes effect for crews built from the updated image. No data migration — existing mailboxes are unaffected.
4. **Rollback**: revert the single-file change; delivery returns to prior behavior. No persisted state depends on the new validation.
