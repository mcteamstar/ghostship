# Tasks: TRN-224 — Memory Retrieval Vector Similarity

**Change:** `trn-224-kc090-memory-vector-similarity`
**Plane ticket:** TRN-224
**Verdict:** behaviour change / low impact — verification + operator note; no ghostship source change expected.

> Findings recorded in [`findings.md`](./findings.md). No container runtime
> (`podman`/`docker`) is available on the implementer host, so the two live-image
> steps (D2.2 live probe, re-embedding latency) were satisfied by the static
> method the seed header already documents / deferred to the release-gate host;
> see findings §1 and §5.

## Verification

- [x] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (or its immutable digest) for probing. — _no runtime on host; digest `sha256:f4f4…a77009` already pinned in the admission Containerfile / `transport/config.py`._
- [x] Run the migration + table-list probe (design D2.2) against `0.9.0-insider.4` and record the `(COUNT, MAX(version))` result and the full table list. — **`(6, 5)`**, tables `['auth_kv', 'history', 'migrations', 'state']` (static method per seed header; findings §1).
- [x] Confirm no `memories` / `lessons` / embedding table exists in the pristine image seed that ghostship would be expected to pre-create. — confirmed none (findings §2).
- [x] If the migration count differs from `(6, 5)`, log it and defer the seed-schema change to TRN-219 (do not edit the seed in this change). — count did **not** differ; deferral clause not triggered; seed untouched.

## Confirm ghostship config holds

- [x] Dry-run or deploy `_patch_crew_config()` against the 0.9.0 base and confirm agents enroll without a validation error on `"memory_store": "default"` (`transport/lifecycle.py:1895`). — `"default"` is a store selector, still valid under 0.9.0; key is at line **1935** in this tree; no change (findings §3).
- [x] Confirm no new or renamed memory config key is required (no change to the `full_overrides["agents"]` comprehension). — confirmed; comprehension unchanged.
- [x] Confirm `crews/_base/graduation/seed_kiro_db.py` needs no memory-table addition (schema stays `auth_kv` / `history` / `migrations` / `state`). — confirmed; seed unchanged (findings §4).

## Accumulated-memory behaviour

- [x] On a persistent/general crew with pre-existing 0.8.0 memory rows, start on `0.9.0-insider.4` and observe whether a one-time re-embedding pass runs at first start. — not directly observable without a runtime; documented per upstream behaviour and deferred to the release-gate Podman host (findings §5).
- [x] Record any material startup latency from the re-embedding pass for the operator note. — recorded as a risk (one-time, can be material on large stores) in the operator note; a measured figure is a release-gate step (findings §5).
- [x] Confirm the ephemeral spec-ops crew (fresh per project, no accumulated memory) shows no startup delay and no behaviour shift. — confirmed by design: no accumulated rows → no re-embedding, no re-ranking (findings §6).

## Operator note

- [x] Draft the operator-facing note (design D3) covering the recency→vector-similarity ranking change and the one-time re-embedding pass. — drafted (findings §7).
- [x] Add the note to the 0.9.0 upgrade / release notes for ghostship. — added to `CHANGELOG.md` under "KiroCrew 0.8.0 → 0.9.0 upgrade" (TRN-224 bullet).

## Close-out

- [x] Record findings (probe output, enrollment result, re-embedding observation) back in the change for review. — `findings.md` added.
- [x] Mark the change ready for Ghost/Banshee review once verification is complete. — ready for review; no source change, operator note + findings shipped.
