# Tasks

## 1. Review release and verify image

- [ ] 1.1 Review the [KiroCrew v0.12.2 release notes](https://github.com/kirodotdev/KiroCrew/releases/tag/v0.12.2) for changes affecting Ghostship's gateway, Kiro CLI, credential injection, policy, or image assumptions; record relevant findings and any no-impact conclusions in the dated dependency review.
- [ ] 1.2 Resolve `ghcr.io/kirodotdev/kirocrew:0.12.2` with `podman manifest inspect` (or the GHCR registry API if Podman is unavailable); record the immutable multi-arch index digest and confirm Linux amd64 and arm64 manifests are present before changing any pin.
- [ ] 1.3 Inspect the v0.12.2 image labels and contents to record its actual Kiro CLI version and SQLite migration rows/table schema; compare them with `seed_kiro_db.py` and the v0.12.0 baseline, and save the observed evidence for the seed annotation and dependency review.

## 2. Advance the image pin and verify the seed

- [ ] 2.1 Update the admission `KC_BASE_IMAGE` argument and both `transport/config.py` defaults to the verified v0.12.2 digest, and refresh their version comments; verify all built-in defaults match and `pytest tests/unit/test_config.py -q` passes.
- [ ] 2.2 Update `seed_kiro_db.py` and the graduation Containerfile annotation with the observed gateway version, actual Kiro CLI version, verification date, and schema result; if migrations or auth-table definitions changed, update the seed and add focused coverage, then verify the seed matches the image schema.

## 3. Refresh dependency and operator records

- [ ] 3.1 Update `config/dependencies.yaml` with the verified image review and evidence, and create `docs/dependency-review-2026-11-14.md` recording the release-note review, digest, CLI version, migration comparison, and compatibility outcome; verify the inventory points to the new evidence and does not claim unverified compatibility.
- [ ] 3.2 Update `docs/configuration.md` and `docs/architecture.md` to show the verified KiroCrew v0.12.2 pin, and add the upgrade details under the existing Ghostship v0.12.2 changelog heading; verify active image documentation no longer describes v0.12.0 or v0.11.2 as the current pin and `VERSION` remains 0.12.2.

## 4. Build and validate the integration

- [ ] 4.1 Build the crew images in an isolated local Podman environment with the verified digest; verify the build completes and the resulting image resolves to the intended KiroCrew base.
- [ ] 4.2 Launch a fresh disposable crew from the rebuilt image and verify gateway readiness, successful Kiro CLI auth injection, enrollment, and completion of a trivial dispatch; record the observed gateway/CLI versions and test result.
- [ ] 4.3 Run the applicable existing unit and end-to-end suites against the local image and verify they pass; run `openspec validate trn-324-upgrade-kirocrew-0-12-2 --type change` and resolve any validation errors.

## Workflow follow-up

- After implementation review and merge, sync the delta spec and archive this change.
- Any Corsair or Carrier deployment, including an adjutant submodule update, requires separate explicit approval.
