# Tasks: TRN-188 KiroCrew 0.8.0 upgrade

## 1. Research phase — wait for 0.8.0 stable release

- [ ] 1.1 Monitor `kirodotdev/KiroCrew` for the 0.8.0 stable tag; update `mcteamstar/KiroCrew` fork once it lands
- [ ] 1.2 Diff `v0.8.0-insider.8` → `v0.8.0` CHANGELOG and source: identify any breaking changes affecting Ghostship's feature surface (spawn API, member enrollment, session attestation, config schema, migration count)
- [x] 1.3 Check `seed_kiro_db.py` migration count against 0.8.0 stable — run `python3 -c "from seed_kiro_db import EXPECTED_MIGRATION_COUNT; print(EXPECTED_MIGRATION_COUNT)"` against a fresh 0.8.0 container
- [ ] 1.4 Document findings in `research/trn-188-kirocrew-080-changelog.md`

## 2. Validation — test TRN-186/187 fixes on 0.8.0 stable

- [ ] 2.1 Build test crew image from `0.8.0` base, launch a crew, verify all 6 personas enroll successfully
- [ ] 2.2 Dispatch Raven, confirm `X-Session-Key` spawn passes attestation (HTTP 200, no `member_identity_unavailable`)
- [ ] 2.3 Dispatch all 6 personas, confirm `slot: "<agent-name>"` routing works
- [ ] 2.4 Open the dashboard (`/crews/*/ui`), confirm crew UI accessible via gs_session cookie

## 3. Implementation — bump KC_BASE_IMAGE

- [x] 3.1 Update `crews/_base/admission/Containerfile` ARG default to `ghcr.io/kirodotdev/kirocrew:0.8.0`
- [x] 3.2 Update `transport/config.py` `kc_base_image` default
- [x] 3.3 Update `config/ghostship.conf.example`
- [x] 3.4 Update `tests/unit/test_config_from_env.py` version assertion
- [x] 3.5 If migration count changed: update `seed_kiro_db.py` and its test

## 4. Deploy and validate on academy

- [ ] 4.1 Update `terran/hyperv/academy/ghostship.conf` `KC_BASE_IMAGE`
- [ ] 4.2 Deploy to academy (`./deploy.sh academy`)
- [ ] 4.3 Run full validation: enrollment, attestation, dispatch, dashboard UI
- [ ] 4.4 Run unit tests: `bash tests/run.sh --unit`

## 5. Ship release/0.6.0

- [ ] 5.1 Commit version bump: `chore: bump KC_BASE_IMAGE to 0.8.0`
- [ ] 5.2 Update TRN-185, TRN-186, TRN-187 to Done in Plane
- [ ] 5.3 Create `release: 0.6.0` commit with version bump in `transport/config.py`
- [ ] 5.4 Tag `v0.6.0` on `release/0.6.0` branch
