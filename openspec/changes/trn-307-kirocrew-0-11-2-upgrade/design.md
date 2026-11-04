# Design

## Context

See proposal.md. The v0.11.2 image is a hotfix over v0.11.1 with no kiro-cli schema changes anticipated. The process mirrors TRN-293 exactly; the only variables are the new digest and the verification result.

## Goals / Non-Goals

**Goals:**
- Advance `KC_BASE_IMAGE` to the v0.11.2 immutable digest
- Verify `seed_kiro_db.py` migration count against the new image (expected: unchanged at `(6, 5)`)
- Update version annotations in `seed_kiro_db.py`, `transport/config.py`, and the spec

**Non-Goals:**
- No KAS adoption — kiro-cli remains the dispatch engine
- No config changes

## Decisions

**Same process as TRN-293.** Obtain digest → verify seed → bump pin → update annotations → rebuild corsair. No architectural decisions.

**Blocking gate: verify seed before committing.** If the migration schema changed (unlikely for a hotfix), the seed must be updated before the image can ship.

## Risks / Trade-offs

- **[Risk]** Image not yet in registry at pylon creation time (released minutes ago). **Mitigation**: `podman manifest inspect` will succeed once the image propagates (~minutes); the implementation task blocks on this.
- **[Risk]** Migration schema changed in hotfix. **Mitigation**: verification step is the first implementation task; if it fails the change is blocked until the seed is updated.
