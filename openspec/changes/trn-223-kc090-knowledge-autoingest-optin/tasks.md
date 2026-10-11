# Tasks

## 1. Confirm the no-op baseline (source audit)

- [ ] 1.1 Re-read `transport/lifecycle.py` `_patch_crew_config()` `full_overrides` dict (~L1885–1965) and confirm it contains no `knowledge` key and no implicit ingest enablement
- [ ] 1.2 Confirm `crews/_base/graduation/seed_kiro_db.py` seeds no knowledge tables/rows (only `auth_kv`, `history`, `state`, `migrations`)
- [ ] 1.3 Confirm `academy/agents/*.json` and `academy/steering/STANDING_ORDERS.md` contain no knowledge-ingest configuration

## 2. Verify the upstream config key before pinning (gates D1)

- [ ] 2.1 Dump the KiroCrew 0.9.0 config schema from the base image to find the real knowledge auto-ingest key, e.g.: `podman run --rm ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4 cat <default config path> | python3 -m json.tool | grep -i -A4 knowledge`
- [ ] 2.2 Record the verified key name/shape (expected `knowledge.auto_ingest`; confirm it is not `knowledge.ingest.enabled` or a per-path boolean set) in `design.md` D1
- [ ] 2.3 Decide D1: Option A (pin `knowledge.auto_ingest=false`) if the key is verified, else Option B (rely on upstream default) and note the open item

## 3. Pin disabled posture (only if D1 = Option A)

- [ ] 3.1 In `transport/lifecycle.py` `_patch_crew_config()`, add `"knowledge": {<verified_key>: False}` to the `full_overrides` literal, between the `auto_update` and `orchestrator` entries, with the explanatory comment from design.md D1
- [ ] 3.2 Confirm no change is needed in `transport/container_scripts/patch_crew_config.py` — `_deep_merge()` already writes any top-level section

## 4. Documentation (required regardless of D1)

- [ ] 4.1 Add a "Knowledge auto-ingest" note to `docs/configuration.md`: ghostship does not enable auto-ingest; it is opt-in under KiroCrew 0.9.0+ (PR #2448); an operator wanting knowledge-from-commits in the mounted worktree must opt in explicitly
- [ ] 4.2 If D1 = Option B, add a one-line open item in the note that the posture relies on the upstream default and is not pinned

## 5. Verification test

- [ ] 5.1 Add a test that builds a representative `full_overrides`, runs `patch_crew_config.patch_config()` against a temp `config.local.json`, and asserts no implicit ingest enablement is present
- [ ] 5.2 If D1 = Option A, extend the test to assert the written JSON has `knowledge.<verified_key> == false` and that other sections (`agent`, `session`, `telemetry`, `agents`) are preserved by the deep-merge
- [ ] 5.3 Run the test suite and confirm green

## 6. Close out

- [ ] 6.1 Update `proposal.md`/`design.md`/`spec.md` with the final D1 decision and the verified key name
- [ ] 6.2 Hand off to Banshee for review via mail (subject carries the verdict and the D1 decision)
