# Tasks

## 1. Review the release and verify the image

- [ ] 1.1 Review the KiroCrew `0.13.0` changelog (in the `v0.13.0-rc.3` tag) and the 2026-11-17 discovery report for changes affecting Ghostship's gateway, Kiro CLI, credential injection, spawn bodies, Bot and member slots, policy or image assumptions. Record each relevant finding and each no-impact conclusion for the dependency review (task 4.2). Verify that the harness-inheritance, `silent`, member-slot and Identity Center profile-lookup changes are each covered.
- [ ] 1.2 Resolve `ghcr.io/kirodotdev/kirocrew:0.13.0-rc.3` with `podman manifest inspect` or the GHCR registry API. Verify the index digest is `sha256:189c57160526f6864120184893d21d4f4905107a3886b8c7f85d93ca27c509e9` and that Linux amd64 and arm64 manifests are present before changing any pin. Record both platform digests.
- [ ] 1.3 Pull the rc.3 image and run a throwaway container from it (not a crew) to record the `dev.kirocrew.kiro-cli.version` label, the `/usr/local/share/kirocrew/kiro-cli-version` marker, and the initialised kiro-cli `migrations` count and maximum version, plus `sqlite_master` table and index definitions. Diff them against `crews/_base/graduation/seed_kiro_db.py` and save the evidence. Verify the evidence states unchanged or lists every difference.

## 2. Advance the image pin and verify the seed

- [ ] 2.1 Update the admission `KC_BASE_IMAGE` ARG in `crews/_base/admission/Containerfile` and the `kc_base_image` default in `transport/config.py` to the rc.3 index digest. Add a comment block recording KiroCrew `0.13.0-rc.3`, the verified Kiro CLI version, the digest and the date. Verify both defaults are identical and that `pytest tests/unit/test_config.py -q` passes.
- [ ] 2.2 Update `seed_kiro_db.py` and the graduation Containerfile annotation with the rc.3 gateway version, Kiro CLI version, verification date and observed migration result. If the migrations or table definitions changed, update the seed and its focused test so they match the image exactly. Verify the seed test passes and that a freshly seeded DB matches task 1.3's schema, including `auth_kv` and `state`.

## 3. Name the crew's backend on transport spawns

- [ ] 3.1 Add one transport helper mapping a crew's recorded `acp_backend` to the gateway request spelling (`kiro`, `claude` and `codex` to themselves, missing to `kiro`, never `kas`), with unit tests for each value and the missing case. Verify the tests pass.
- [ ] 3.2 Add the mapped `backend` to the `/api/spawn` body in single dispatch (`transport/tools.py`), batch dispatch (`transport/lifecycle.py` `_dispatch_batch`) and the Captain Raven check-in (`transport/captain_engine.py`). Leave `ghostship-spawn` unchanged. Extend the existing dispatch, batch and Captain tests to assert the field for kiro, claude and missing-backend crews. Verify that a gateway 4xx refusal is returned as an error and not retried without the field. Run `pytest tests/unit -q` and verify it passes.
- [ ] 3.3 Document in the `dispatch` and `captain` tool descriptions and `docs/architecture.md` that transport spawns name the crew's backend. Verify the text matches the `crew-acp-backend` delta.

## 4. Refresh dependency and operator records

- [ ] 4.1 Update `config/dependencies.yaml` with the rc.3 pin, the evidence from tasks 1.2 and 1.3, and the pending final-release gate. Verify it does not claim final-release compatibility.
- [ ] 4.2 Create `docs/dependency-review-<date>.md` recording the release review (1.1), digest and platforms (1.2), Kiro CLI version and migration comparison (1.3), the backend-pin decision, and the compatibility outcome once group 5 has run. Verify every claim cites its evidence.
- [ ] 4.3 Update `docs/configuration.md` (`KC_BASE_IMAGE` default) and `docs/architecture.md` (crew image version). Add a KiroCrew 0.13 upgrade entry to `CHANGELOG.md` covering the new pin, the backend field and the need to recreate crews to adopt the image. Verify no active documentation still names v0.12.2 as the current pin.

## 5. Build and validate the integration

- [ ] 5.1 Rebuild with `ghostship install` from `release/0.13.0`. Verify `localhost/spec-ops:latest` labels report KiroCrew `0.13.0-rc.3` and the Kiro CLI version from 1.3, and that the transport reports healthy.
- [ ] 5.2 Run a fresh kiro Identity Center login (`ghostship auth login kiro --method identity-center --yes`). Verify the stored credential's `state` holds `api.codewhisperer.profile` and that the transport log shows the profile wait completed, not a timeout.
- [ ] 5.3 Launch a fresh kiro crew. Verify gateway readiness, `kiro_signin.ok: true` in `crews`, and that one dispatch naming `backend: "kiro"` and one raw spawn without a backend run on the same harness (compare each run's recorded backend). Verify both complete, then run a Captain `willy` order for one check-in and verify Raven's spawn on `member-raven` succeeds.
- [ ] 5.4 Launch a fresh claude crew. Verify a dispatch completes and its run records the `claude` backend.
- [ ] 5.5 Run `scripts/run.sh --unit --integration` and the live `--e2e` suite against the rebuilt transport. Run `openspec validate upgrade-kirocrew-0-13-0 --type change --strict`. Verify all pass, and record the results in the dependency review.

## 6. Release gate: final KiroCrew 0.13.0

- [ ] 6.1 Once `ghcr.io/kirodotdev/kirocrew:0.13.0` is published, repeat tasks 1.2 and 1.3 against it. Re-pin both defaults (2.1), re-verify the seed (2.2), and update the records (4.1 to 4.3). Verify no `0.13.0-rc` reference remains in the pins or active documentation.
- [ ] 6.2 Repeat tasks 5.1 to 5.5 on the final digest and record the outcome in the dependency review. Verify all checks pass before Ghostship 0.13.0 is tagged.

## Workflow follow-up

- After review and merge, sync the delta specs and archive this change.
- A follow-up change covers dispatch visibility in the dashboard: the discovery's watch-chat option, and the upstream owner-tier work-dispatch route.
- Any deployment beyond this host requires separate explicit approval.
