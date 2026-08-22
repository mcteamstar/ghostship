# Tasks — trn-18-operator-tier

## Task 1 — Create default policy template ✅

File: `academy/policies/default.json` (new)

Write the baseline security policy for the `kirocrew` composition as
specified in design.md §Default policy baseline. Platform-integrity focus only:
- `commands.deny`: git push, git remote add, gh, pipe-to-shell curl/wget
- `channels.deny`: all messaging integrations
- No `sandbox`, `filesystem`, or `network` restrictions
- `version: "1"`

## Task 2 — Create research and strict policy variants ✅

Files: `academy/policies/research.json`, `academy/policies/strict.json` (new)

`research.json` — same as default (open). Included as a starting point for
operators customising research crew behaviour.

`strict.json` — example tighter policy for operators who want it. Not
the default. Include: `sandbox.min_level: "standard"`, `filesystem.write`
allow-mode with `~/workplace`, `~/.kiro`, `~/.local/share/kiro-cli`,
`/var/mail`, `/tmp`, broader `commands.deny` (add `sudo`, `rm -rf /`).
Add a comment in the file noting it is an example, not a default.

## Task 3 — Implement `_inject_policy()` in transport ✅

File: `transport/server.py`

Implement the `_inject_policy(podman, container, composition, admiral_secret)`
helper as specified in design.md §`_inject_policy()` implementation:
- Load policy template from `/policies/<composition>.json`, fall back to
  `/policies/default.json`
- Compute HMAC-SHA256 signature over canonical (json.dumps sort_keys=True)
  policy body using `admiral_secret`
- Build `admission_policy.json` with `require_policy_signature: true` and
  the signature as a trust key
- Write both files to `~/.kiro/crew/` inside the container via
  `container_exec_checked`
- Return the policy `version` string
- Log success; warn (don't raise) on failure

**Before writing the admission_policy.json structure**, verify the exact field
names (`trust_keys`, `id`, `key`, `require_policy_signature`) against the
KiroCrew source in the upstream repo (`packages/kiro-crew-core/` or similar).
If the schema differs from the design, update the design and this task before
proceeding. An incorrect schema means signing silently does nothing.

## Task 4 — Call `_inject_policy()` from `_finish_crew_setup()` ✅

File: `transport/server.py`

In `_finish_crew_setup`, after the `admiral_secret` is injected and saved to
the registry:
1. Call `_inject_policy(podman, container, composition, admiral_secret)`
2. Store the returned `policy_version` in the registry entry
3. Include `policy_version` in the `_finish_crew_setup` return dict

Wrap the call in try/except — policy injection failure MUST NOT abort launch.

## Task 5 — Add `policy_version` to `launch()` response and `crews()` ✅

File: `transport/server.py`

- `launch()` return value: include `policy_version` from the registry if
  present
- `crews()` per-crew entry: include `policy_version` from the registry entry
  if present; omit the field for crews that pre-date this change

## Task 6 — Mount `academy/policies/` in transport container ✅

Files: `docker-compose.yml`, `install.sh`

Add a bind mount that maps `academy/policies/` on the host to `/policies/`
inside the transport container, following the same pattern as `/agents/`,
`/skills/`, and `/steering/`. Verify the mount is read-only.

## Task 7 — Write tests for policy injection ✅

File: `transport/test_transport.py`

Add tests covering:
- Policy injected with correct composition-specific template when found
- Policy falls back to default when composition template not found
- Admission policy written alongside security policy
- `launch()` response includes `policy_version`
- `crews()` entry includes `policy_version`
- Policy injection failure (container_exec raises) is caught, logged, and
  does not abort launch
- `_inject_policy` HMAC uses `admiral_secret` and produces deterministic
  output for a fixed input

## Task 8 — Sync specs and archive (Reaper)

Leave for Reaper dispatch after all Ghost tasks are complete and verified.
Do not implement this task — it is a reminder that Reaper closes the change.

## Task 9 — Update docs ✅

Files: `docs/architecture.md`, `docs/auth.md`

- `docs/architecture.md`: add a "Operator governance" section documenting that
  Ghostship uses the KiroCrew operator tier, how policy files are injected at
  setup, and how to customise per composition
- `docs/auth.md`: add policy signing alongside mail signing in the
  `admiral_secret` section — same key, two uses
