# Tasks

## 1. Confirm the no-op baseline (source audit)

- [x] 1.1 Re-read `transport/lifecycle.py` `_patch_crew_config()` `full_overrides` dict (~L1912–1945) and confirm it contains no `knowledge` key and no implicit ingest enablement — confirmed: `grep -ni knowledge transport/lifecycle.py` returns nothing
- [x] 1.2 Confirm `crews/_base/graduation/seed_kiro_db.py` seeds no knowledge tables/rows (only `auth_kv`, `history`, `state`, `migrations`) — confirmed: only those four `CREATE TABLE`s + 6 migration rows
- [x] 1.3 Confirm `academy/agents/*.json` and `academy/steering/STANDING_ORDERS.md` contain no knowledge-ingest configuration — confirmed: only unrelated prose hit (`independent-review.md` "no knowledge of the others")

## 2. Verify the upstream config key before pinning (gates D1)

- [x] 2.1 Attempted the podman image dump; podman unavailable in the build/CI sandbox. Verified instead against the gateway package baked into the pinned base image — `kiro_crew` 0.9.0rc4 (= `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`), `kiro_crew/config/memory_sections.py::KnowledgeConfig`
- [x] 2.2 Recorded the verified shape in `design.md` D1: there is **no bare `knowledge.auto_ingest` boolean**. Real ingest toggles are `knowledge.auto_ingest_artifacts` (bool, default `False`) and `knowledge.auto_add_documents` (bool, default `False`, formerly `auto_ingest_doc_links`). CHANGELOG confirms "auto-ingest is opt-in… ingests nothing until you switch it on"
- [x] 2.3 Decided D1 = **Option B** — the assumed key is unverifiable (does not exist), so pinning it would be an inert dead key; rely on the verified upstream default and record the open item as a CI tripwire

## 3. Pin disabled posture (only if D1 = Option A)

- [N/A] 3.1 Skipped — D1 = Option B. No `knowledge.auto_ingest` key exists upstream to pin; adding it would be a dead key. `transport/lifecycle.py` is unchanged
- [N/A] 3.2 Not applicable (no `knowledge` section added) — the `_deep_merge()` capability remains available for a future operator opt-in

## 4. Documentation (required regardless of D1)

- [x] 4.1 Added a "Knowledge auto-ingest" note to `docs/configuration.md`: ghostship does not enable auto-ingest; it is opt-in under KiroCrew 0.9.0+ (PR #2448); an operator wanting knowledge-from-commits must opt in explicitly
- [x] 4.2 D1 = Option B: the note states the posture relies on the verified upstream default and is **not** pinned, and points at the CI tripwire test for the open item

## 5. Verification test

- [x] 5.1 Added `tests/unit/test_trn223_knowledge_autoingest.py` — builds a representative `full_overrides`, runs real `patch_crew_config.patch_config()` against a temp `config.local.json`, asserts no `knowledge` section is written and no implicit enablement
- [x] 5.2 D1 = Option B: instead of asserting a pin, the test asserts (a) the assumed `auto_ingest` field does not exist in `KnowledgeConfig`, (b) the real ingest toggles default to `False`, and (c) the deep-merge preserves `agent`, `session`, `telemetry`, `agents`
- [x] 5.3 Ran the test suite — `python3 -m unittest tests.unit.test_trn223_knowledge_autoingest` = 4 tests, OK (green). pytest is not installed in this sandbox; unittest is the stdlib runner the repo's tests already use

## 6. Close out

- [x] 6.1 Updated `proposal.md`/`design.md`/`spec.md` (both delta specs) with the final D1 = Option B decision and the verified key names/shapes
- [x] 6.2 Hand off to Banshee for review via mail (subject carries the verdict and the D1 decision)
