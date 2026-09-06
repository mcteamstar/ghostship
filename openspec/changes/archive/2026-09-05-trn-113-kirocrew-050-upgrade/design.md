## Context

Ghostship pins `ghcr.io/kirodotdev/kirocrew:0.4.0` in two places: the crew base
image (`crews/_base/admission/Containerfile`) and the ephemeral login container
(`KC_BASE_IMAGE`). The pre-seeded kiro-cli DB in `crews/_base/graduation/seed_kiro_db.py`
hard-codes the exact schema and migration rows from 0.4.0. The full breaking-change
analysis is in `docs/kirocrew-v0.5.0-migration.md`; none of the ten breaking changes
touch code paths ghostship uses.

The only genuinely risky item is the pre-seeded DB: if 0.5.0's kiro-cli added
migration rows and the seed is not updated, crews silently start with an
under-migrated DB. Everything else is low-effort confirmation.

## Goals / Non-Goals

**Goals:**
- Bump the crew base image and login container image to 0.5.0
- Re-verify the pre-seeded DB before any pin is committed
- Confirm policy templates, agent specs, and MCP pooling are unaffected by 0.5.0's stricter validators

**Non-Goals:**
- See proposal.md Non-Goals — fleet policy, session_send, conductor agent, Node.js / openspec pin bumps

## Decisions

### Decision 1: Verify-first ordering — DB check before any pin change

The pre-seeded DB check (Step 1) must complete before any Containerfile or
config is modified. If the DB schema changed, `seed_kiro_db.py` must be updated
first and the result committed independently. This avoids a situation where the
pin is bumped and images are rebuilt with a stale seed.

Alternative considered: bump pin first, run tests, fix DB if they fail. Rejected
— DB migration failures inside a running crew are silent and hard to detect from
the outside; catching them before the rebuild is cheaper.

### Decision 2: Validation steps are read-only confirms, not rewrites

Steps 5–7 (policy templates, agent specs, MCP pooling) are expected to pass
without edits. The tasks are structured as "read and confirm" with an edit path
only if a specific problem is found. This keeps the change scope small and makes
it easy to see at a glance what actually needed changing.

### Decision 3: Single commit or two commits depending on DB outcome

- **DB unchanged**: one commit covering the pin bump, stale reference refresh,
  and CHANGELOG entry.
- **DB schema/rows changed**: two commits — first for the seed update (with a
  commit message noting the migration count), then for the pin bump — so the DB
  fix is independently reviewable.

### Decision 4: No new capability changes

0.5.0 introduces `session_send`, a conductor agent, and fleet policy. None of
these are adopted here. The spec deltas for this change are purely version
reference updates and validation confirmations — no new behaviour is introduced
or required by this upgrade.

## Risks / Trade-offs

**Risk: Pre-seeded DB mismatch** → The only non-trivial risk. Mitigation: Step 1
runs first, records the migration count, and compares against the current seed
expectation `(10, 9)` before any pin is touched. If counts differ, the seed is
updated before proceeding.

**Risk: Policy validator now hard-fails on bad keys** → Low. The three policy
templates in `academy/policies/` were validated against 0.4.0 (which silently
ignored malformed keys). Step 5 re-reads them against the 0.5.0 schema
requirements. Expected to pass with no edits.

**Risk: Agent spec reader now hard-fails on malformed specs** → Low. All six
agent JSONs are maintained and well-formed. Step 6 is a read-confirm pass.

**Risk: Rebuild failure** → If any layer fails to build, the old pin is still
in place and the transport still works. Rollback is a revert of the Containerfile
change.
