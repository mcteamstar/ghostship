## Why

A holistic code review (docs/research/code-review.md, 2026-08-22) surfaced 31
findings. This change addresses the high and medium items that are well-scoped
enough to land together without a full design pass.

## What Changes

### Immediate (high)

**Agent JSONs: `radio` → `ghostship-mail`**
All 6 agent JSON files (`ghost.json`, `spectre.json`, `banshee.json`,
`wraith.json`, `reaper.json`, `raven.json`) reference
`skills/radio/SKILL.md`. The skill was renamed to `ghostship-mail` in
SRV-68. Every agent that tries to load the skill file finds nothing. Fix:
replace `radio` with `ghostship-mail` in all prompt strings.

**Delete `academy/steering/ORDERS.md`**
An old mbox-era steering document that contradicts `STANDING_ORDERS.md` on
how mail works. Both are copied to `~/.kiro/steering/` at crew launch and
agents receive contradictory instructions. Delete it.

**`_save_registry` atomic write**
`Path.write_text()` truncates then writes — a crash between the two ops
leaves a corrupted `crews.json`. Fix: write to a `.tmp` file then
`os.replace()` atomically.

**`launch()` TOCTOU**
Two concurrent `launch("same-id")` calls can both pass the existence check
before either inserts into the registry, creating duplicate containers.
Fix: hold a single lock across both checks and pre-insert a `{status:
"launching"}` placeholder before releasing. Roll back the placeholder on
failure.

**`_handle_file_put` bundle flag**
The upload token verifier calls `_verify_file_token(crew_id, path, expires,
sig)` without passing `bundle`. The download verifier passes it. This allows
a `supply` URL (signed with `bundle=False`) to be submitted with `?bundle=1`
appended and accepted, switching the operation to a git-bundle-clone. Fix:
pass `bundle` flag in `_handle_file_put`'s call to `_verify_file_token`.

**`steer()` / Raven `mode` discrepancy**
Raven's prompt tells it to call the steer endpoint with `{"message": ...,
"mode": "follow_up"}` but transport's `steer()` sends `{"message": ...}`
with no `mode` field. One side must align to the other. Decision pending
confirmation of whether `mode` is required by the gateway API — if not,
remove from the Raven prompt; if yes, add to `steer()`.

### Medium

- `schedule()` missing `CrewUnresponsiveError` in exception catch —
  unresponsive crew propagates as unhandled exception rather than
  `{"error": ...}`
- `_mint_cookie` hardcodes `mc_token_5476` instead of
  `f"mc_token_{PORT}"` — fails silently on non-default port
- `_read_all_mail_subjects` legacy mbox branch unguarded — add
  `try/except OSError` consistent with Maildir branch
- `_MBOX_MISSING_MARKER` constant defined but never used — remove
- `_pickup_list` return type annotation says `dict | list` but always
  returns `dict` — fix annotation
- README: `nuke` appears in SDD lifecycle diagram — per
  `crew-lifecycle/spec.md` the diagram SHALL NOT show `nuke` as the
  final step. Move `nuke` to a separate "intentional teardown" section.
- `openspec/specs/crew-lifecycle/spec.md` uses `crew_type` parameter
  name but `launch()` uses `composition` — update spec
- `openspec/specs/mail/spec.md` "guard against `From ` lines corrupting
  mbox parsing" requirement is dead — Maildir doesn't parse `From ` as
  message boundaries. Mark as superseded or remove.
- `docs/auth.md`: add `admiral_secret` threat model — plaintext in
  `crews.json`, single-user risk acceptable, multi-operator risk documented

## Decisions

- `steer()` mode field: check the gateway API spec or empirically test
  whether `mode` is required before deciding which side to fix.

## Capabilities

### Modified Capabilities
- `agent-personas`: prompt corrections (radio→ghostship-mail)
- `mcp-server`: error handling improvements
- `file-transfer`: bundle flag fix
- `crew-lifecycle`: launch TOCTOU fix, spec naming alignment
- `mail`: dead spec requirement removal

## Impact

- `academy/agents/*.json` — 6 files
- `academy/steering/ORDERS.md` — deleted
- `transport/server.py` — atomic registry write, launch TOCTOU, bundle flag,
  mint_cookie port fix, schedule error catch, mail subjects guard, dead constant
- `transport/test_transport.py` — tests for new behaviors
- `openspec/specs/crew-lifecycle/spec.md` — crew_type → composition
- `openspec/specs/mail/spec.md` — remove dead mbox escaping requirement
- `README.md` — lifecycle diagram fix
- `docs/auth.md` — admiral_secret documentation
