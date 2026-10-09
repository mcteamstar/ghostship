# Design: TRN-188 KiroCrew 0.8.0 Upgrade

## Context

Ghostship `release/0.6.0` is pinned to `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.8.0-insider.8`.
The TRN-185/186/187 attestation and enrollment fixes were developed and tested against that insider
build. Before the release branch can ship to academy, we must confirm the fixes hold on the stable
`0.8.0` image and that no new breaking changes affect Ghostship's integration surface.

The upgrade touches a handful of static config values (Containerfile ARG, Python default, example
conf, unit test assertion) — mechanically simple — but is gated on a validation gate that must run
against a live 0.8.0 container. Some implementation tasks (3.1–3.5) are already checked off,
meaning the version strings have been bumped; the remaining work is research, live validation, and
academy deploy.

See `proposal.md` for motivation and full impact file list.

## Goals / Non-Goals

**Goals:**

- Confirm `0.8.0` stable introduces no breaking changes for Ghostship's spawn API, member
  enrollment, session attestation, config schema, or migration count
- Validate TRN-186/187 fixes (X-Session-Key attestation, `enrolled_agents` enrollment) work
  end-to-end on 0.8.0 stable before academy deploy
- Land `KC_BASE_IMAGE=0.8.0` across all config files and ship `release/0.6.0` to academy

**Non-Goals:**

- Changing the member enrollment approach or attestation mechanism (unless research reveals
  a 0.8.0 breaking change forces it)
- Any Ghostship feature work unrelated to the base image bump
- Upgrading past 0.8.0 stable in this change

## Decisions

### D1: Research before code freeze

**Decision:** Treat this as research-first. No academy deploy until CHANGELOG diff and live
container validation are complete.

**Rationale:** The insider→stable gap is unknown in advance. A silent breaking change in the
spawn API or session attestation surface would corrupt a live academy crew. The validation gate
(tasks 2.1–2.4) is the only reliable signal.

**Alternative considered:** Bump and deploy optimistically, then roll back if issues are found.
Rejected — a bad base image on academy breaks all active crew sessions and requires a full
redeploy cycle to recover.

---

### D2: Validate migration count via live container, not source inspection

**Decision:** Run `seed_kiro_db.py` against an actual 0.8.0 container to get the expected
migration count rather than inferring it from the CHANGELOG.

**Rationale:** Migration counts are fragile to source-read — off-by-one is common, and the
consequence (container startup failure on a wrong count assertion) is a hard blocker. A 60-second
container probe eliminates ambiguity. Task 1.3 is already checked off, confirming this was done.

**Alternative considered:** Read the Alembic migration files directly and count. Rejected as
error-prone — squash migrations and multi-head histories make manual counting unreliable.

---

### D3: Scope validation to Ghostship's integration surface only

**Decision:** The CHANGELOG diff (task 1.2) focuses only on: spawn API, member enrollment,
session attestation, config schema, migration count. General KiroCrew feature changes outside
that surface are noted but not acted on.

**Rationale:** Full compatibility testing of KiroCrew itself is not Ghostship's responsibility.
Ghostship's integration surface is well-defined by TRN-185/186/187, and bounded validation is
faster and less risky than a broad regression sweep.

---

### D4: Academy deploy is the final validation gate, not a staging environment

**Decision:** Validate on academy directly (task 4.x) rather than a separate staging crew.

**Rationale:** Ghostship has no dedicated staging environment. Academy is the integration target
and running a validation deploy there before the release tag is the established pattern for
pylon changes. The rollback path (revert `KC_BASE_IMAGE` to insider.8 and redeploy) is
straightforward.

## Risks / Trade-offs

**[Risk] 0.8.0 stable introduces a breaking spawn API change** → Mitigation: CHANGELOG diff
(task 1.2) catches this before any deploy. If a break is found, scope expands and TRN-188 blocks
until a fix is landed.

**[Risk] Migration count differs between insider.8 and stable** → Mitigation: Task 1.3 (already
complete) confirms the count via live container. `seed_kiro_db.py` and its test are updated if
needed (task 3.5, also checked off).

**[Risk] TRN-186/187 attestation fixes are accidentally reverted by a 0.8.0 internal change**
→ Mitigation: Tasks 2.2–2.3 directly re-verify the attestation and enrollment paths on stable
before deploy.

**[Risk] Academy crew sessions disrupted during validation deploy** → Mitigation: Academy is a
low-traffic environment. Time the deploy to a low-activity window. Rollback is a single config
change + redeploy.

**[Trade-off] Research phase adds calendar time before ship** → Accepted. Shipping a broken
`release/0.6.0` to academy is a worse outcome than the delay.

## Migration Plan

1. **Await 0.8.0 stable tag** — monitor `kirodotdev/KiroCrew`; update fork mirror once landed
2. **CHANGELOG diff** — document findings in `research/trn-188-kirocrew-080-changelog.md`
3. **Container validation** — build from 0.8.0 base, run tasks 2.1–2.4 checks
4. **Config bump** — tasks 3.1–3.5 (mostly complete); apply any migration count corrections
5. **Academy deploy** — update `terran/hyperv/academy/ghostship.conf`, run `./deploy.sh academy`
6. **Full validation on academy** — enrollment, attestation, dispatch, dashboard UI, unit tests
7. **Release** — commit version bump, tag `v0.6.0`, update TRN-185/186/187 in Plane

**Rollback:** Revert `KC_BASE_IMAGE` to `0.8.0-insider.8` in all config files, redeploy academy.
No data migration is involved; rollback is instantaneous.

## Open Questions

- What is the exact `v0.8.0` release date? (Does not change the approach — research phase begins
  immediately on tag; ship date is blocked on it but not on design decisions.)
