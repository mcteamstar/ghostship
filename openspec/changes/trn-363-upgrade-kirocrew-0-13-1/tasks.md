# Tasks

## 1. Verify the upstream release and its trust boundary

- [x] 1.1 Resolve KiroCrew 0.13.1 to its OCI index and amd64/arm64 manifests; inspect the published image metadata for the actual bundled Kiro CLI version and initialized SQLite migration rows, tables, and indexes, and record the digests and evidence on TRN-363.
- [x] 1.2 Review the v0.13.0-to-v0.13.1 upstream changes that touch Ghostship's enabled paths, including restart/cancel message handoff and local sign-in token delivery; record why the shipped configurations keep token access within the intended trust boundary, and stop the upgrade if that cannot be established.

## 2. Match the auth seed to the candidate CLI

- [x] 2.1 Compare the candidate CLI database with `crews/_base/graduation/seed_kiro_db.py`; update its release/schema verification annotation and, only if the actual schema changed, update the seeded migrations, tables, or indexes, then verify `pytest tests/unit/test_seed_kiro_db.py` passes.
- [x] 2.2 Run the candidate image's auth-injection smoke check against disposable data with test-only `auth_kv` and Identity Center `state` rows; verify both are stored and the candidate CLI opens the database without schema or migration errors. Verify real authentication in Task 5 on the installed candidate.

## 3. Advance the pinned base image

- [x] 3.1 Update the verified 0.13.1 index digest and release metadata in `crews/_base/admission/Containerfile` and synchronize every shipped `KC_BASE_IMAGE` default; verify the default resolves to the same digest while an explicit `KC_BASE_IMAGE` override remains effective.
- [x] 3.2 Build the admission image from the new default and inspect its resolved base digest and bundled Kiro CLI version; verify the build and image-inspection checks pass before proceeding. Built from the pinned multi-arch index (`sha256:080c8141…`) for amd64 and arm64; both images report KiroCrew 0.13.1, revision `e9178c0`, and `kiro-cli-chat 2.27.1`.

## 4. Refresh dependency and runtime records

- [x] 4.1 Update the KiroCrew and derived Kiro CLI entries in `dependencies.yaml` with the verified 0.13.1 digest, CLI version, schema/runtime evidence, outcome, and next review date; verify `python3 scripts/dependency_check.py validate` and run `check`, confirming the changed entries have no declaration drift and recording any unrelated global lookup limits. Inventory validation passed; the KiroCrew entries resolve to the pinned 0.13.1 candidate, while the full review is incomplete because unrelated Docker Hub scans hit pagination caps.
- [x] 4.2 Update runtime documentation and the current 0.13.1 changelog section with the adopted version, digest, behavior changes relevant to Ghostship, and backend validation limits; verify references match the pin and do not add standalone dependency-review documents.

## 5. Validate release behavior

- [ ] 5.1 Install the candidate build on Corsair and Carrier through their normal deployment paths, then run fresh/disposable-crew checks for authentication, dispatch, pickup, stop/wake, and a follow-up task; record results and any unavailable backend coverage on TRN-363.
- [ ] 5.2 Confirm existing crew containers and home volumes were left intact, and verify rollback restores the 0.13.0 image and its matching seed without opening candidate-migrated data in the old image.

## Workflow follow-up

- After implementation review, sync and archive this change so `installation/crew-images` records the verified 0.13.1 contract.
