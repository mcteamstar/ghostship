# Tasks: TRN-224 — Memory Retrieval Vector Similarity

**Change:** `trn-224-kc090-memory-vector-similarity`
**Plane ticket:** TRN-224
**Verdict:** behaviour change / low impact — verification + operator note; no ghostship source change expected.

## Verification

- [ ] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (or its immutable digest) for probing.
- [ ] Run the migration + table-list probe (design D2.2) against `0.9.0-insider.4` and record the `(COUNT, MAX(version))` result and the full table list.
- [ ] Confirm no `memories` / `lessons` / embedding table exists in the pristine image seed that ghostship would be expected to pre-create.
- [ ] If the migration count differs from `(6, 5)`, log it and defer the seed-schema change to TRN-219 (do not edit the seed in this change).

## Confirm ghostship config holds

- [ ] Dry-run or deploy `_patch_crew_config()` against the 0.9.0 base and confirm agents enroll without a validation error on `"memory_store": "default"` (`transport/lifecycle.py:1895`).
- [ ] Confirm no new or renamed memory config key is required (no change to the `full_overrides["agents"]` comprehension).
- [ ] Confirm `crews/_base/graduation/seed_kiro_db.py` needs no memory-table addition (schema stays `auth_kv` / `history` / `migrations` / `state`).

## Accumulated-memory behaviour

- [ ] On a persistent/general crew with pre-existing 0.8.0 memory rows, start on `0.9.0-insider.4` and observe whether a one-time re-embedding pass runs at first start.
- [ ] Record any material startup latency from the re-embedding pass for the operator note.
- [ ] Confirm the ephemeral spec-ops crew (fresh per project, no accumulated memory) shows no startup delay and no behaviour shift.

## Operator note

- [ ] Draft the operator-facing note (design D3) covering the recency→vector-similarity ranking change and the one-time re-embedding pass.
- [ ] Add the note to the 0.9.0 upgrade / release notes for ghostship.

## Close-out

- [ ] Record findings (probe output, enrollment result, re-embedding observation) back in the change for review.
- [ ] Mark the change ready for Ghost/Banshee review once verification is complete.
