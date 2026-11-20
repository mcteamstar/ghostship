# Tasks

## 1. Review the release and verify the image

- [ ] 1.1 Review the KiroCrew `v0.13.0` stable changelog and the 2026-11-17 discovery report for changes affecting Ghostship's gateway, Kiro CLI, credential injection, spawn bodies, Bot and member slots, policy or image assumptions. Record each relevant finding and each no-impact conclusion on the TRN-322 Plane ticket (task 4.2). Verify that the harness-inheritance, `silent`, member-slot and Identity Center profile-lookup changes are each covered.
- [x] 1.2 Resolve `ghcr.io/kirodotdev/kirocrew:0.13.0` with `podman manifest inspect` or the GHCR registry API. Record the stable index digest and verify Linux amd64 and arm64 manifests before changing any pin. Record both platform digests.
- [x] 1.3 Pull the stable `0.13.0` image and run a throwaway container from it (not a crew) to record the `dev.kirocrew.kiro-cli.version` label, the `/usr/local/share/kirocrew/kiro-cli-version` marker, and the initialised kiro-cli `migrations` count and maximum version, plus `sqlite_master` table and index definitions. Diff them against `crews/_base/graduation/seed_kiro_db.py` and save the evidence. Verify the evidence states unchanged or lists every difference.

## 2. Advance the image pin and verify the seed

- [x] 2.1 Update the admission `KC_BASE_IMAGE` ARG in `crews/_base/admission/Containerfile` and the `kc_base_image` default in `transport/config.py` to the verified stable index digest from task 1.2. Add a comment block recording KiroCrew `0.13.0`, the verified Kiro CLI version, the digest and the date. Verify both defaults are identical and that `pytest tests/unit/test_config.py -q` passes.
- [x] 2.2 Update `seed_kiro_db.py` and the graduation Containerfile annotation with the stable gateway version, Kiro CLI version, verification date and observed migration result. If the migrations or table definitions changed, update the seed and its focused test so they match the image exactly. Verify the seed test passes and that a freshly seeded DB matches task 1.3's schema, including `auth_kv` and `state`.

## 3. Name the crew's backend on transport spawns

- [x] 3.1 Add one transport helper mapping a crew's recorded `acp_backend` to the gateway request spelling (`kiro`, `claude` and `codex` to themselves, missing to `kiro`, never `kas`), with unit tests for each value and the missing case. Verify the tests pass.
- [x] 3.2 Add the mapped `backend` to all five transport `/api/spawn` paths: single dispatch, batch dispatch, Captain Raven check-in, scheduled immediate dispatch, and scheduled tick dispatch. Leave `ghostship-spawn` unchanged. Test Kiro, Claude, Codex, and legacy fallback at the shared Transport spawn boundary used by all five paths. Verify a gateway 4xx refusal is returned as an error and not retried without the field. Run `pytest tests/unit -q` and verify it passes.
- [x] 3.3 Document in the `dispatch` and `captain` tool descriptions and `docs/architecture.md` that transport spawns name the crew's backend. Verify the text matches the `crew-acp-backend` delta.

## 4. Refresh dependency and operator records

- [x] 4.1 Update `dependencies.yaml` with the stable `0.13.0` pin and a concise compatibility summary.
- [ ] 4.2 Record on the TRN-322 Plane ticket the release review (1.1), digest and platforms (1.2), Kiro CLI version and migration comparison (1.3), the backend-pin decision, and the compatibility outcome once group 5 has run. Link to supporting evidence in Plane and keep detailed review notes there.
- [x] 4.3 Update `docs/configuration.md` (`KC_BASE_IMAGE` default) and `docs/architecture.md` (crew image version). Add a KiroCrew 0.13 upgrade entry to `CHANGELOG.md` covering the new pin, the backend field and the need to recreate crews to adopt the image. Verify no active documentation still names v0.12.2 as the current pin.

## 5. Build and validate the integration

- [x] 5.1 Rebuild with `ghostship install` from `release/0.13.0`. Verify `localhost/spec-ops:latest` labels report KiroCrew `0.13.0` and the Kiro CLI version from 1.3, and that the transport reports healthy.
- [x] 5.2 Run a fresh kiro Identity Center login (`ghostship auth login kiro --method identity-center --yes`). Verify the stored credential's `state` holds `api.codewhisperer.profile` and that the transport log shows the profile wait completed, not a timeout.
- [x] 5.3 Launch a fresh kiro crew. Verify gateway readiness, `kiro_signin.ok: true` in `crews`, and that one dispatch naming `backend: "kiro"` and one raw spawn without a backend run on the same harness (compare each run's recorded backend). Verify both complete, then run a Captain `willy` order for one check-in and verify Raven's spawn on `member-raven` succeeds.
- [x] 5.4 Launch a fresh claude crew. Verify a dispatch completes and its run records the `claude` backend.
- [x] 5.5 Run `scripts/run.sh --unit --integration` and the live `--e2e` suite against the rebuilt transport. Run `openspec validate trn-322-upgrade-kirocrew-0-13-0 --type change --strict`. Verify all pass, and record the results on the TRN-322 Plane ticket.

## Workflow follow-up

- After review and merge, sync the delta specs and archive this change.
- A follow-up change covers dispatch visibility in the dashboard: the discovery's watch-chat option, and the upstream owner-tier work-dispatch route.
- Any deployment beyond this host requires separate explicit approval.
