# Design

## Context

See `proposal.md` for the motivation. The current production pin is KiroCrew 0.13.0 at index digest `sha256:f4c6c72656e60ed21fd02a86d2b631735660d58d9d0806f7b464acbd3ccb9a26`; the bundled Kiro CLI is recorded as 2.27.1. The image is selected in `crews/_base/admission/Containerfile`, while the install configuration passes `KC_BASE_IMAGE` through to the build. `crews/_base/graduation/seed_kiro_db.py` pre-creates the Kiro CLI database schema used by `transport/container_scripts/inject_auth.py`. Existing crews have their own containers and persistent home volumes, so changing the default affects newly built crews and must not trigger their recreation.

## Goals / Non-Goals

**Goals:**

- Adopt only a stable 0.13.1 image whose index and platform manifests are verified and whose immutable digest is recorded consistently.
- Preserve first-launch authentication by matching the seed database to the actual bundled CLI migration state and schema.
- Review upstream runtime and security changes that interact with Ghostship's enabled features before accepting the pin.
- Make rollback and rollout evidence clear without changing or deleting existing crew homes.

**Non-Goals:**

- Upgrade KiroCrew adapters, OpenSpec, Node, or other independently versioned dependencies.
- Add upstream app integrations, credential forwarding, or new agent capabilities as part of this image bump.
- Migrate or recreate existing crews automatically.

## Decisions

### Pin the verified multi-architecture index digest

Resolve the stable 0.13.1 release tag to its OCI index and amd64/arm64 manifests. Record the verified index digest, bundled Kiro CLI version, and verification date in the admission image comment and dependency inventory. Keep the Containerfile default, shipped `KC_BASE_IMAGE` default, and login-container image resolution aligned; preserve explicit operator overrides.

**Alternative considered:** pin the version tag. A tag can move, so it does not guarantee later builds use the image that was reviewed.

### Treat the actual CLI schema as the seed authority

Inspect the 0.13.1 image's initialized CLI database and active chat migrations for each supported architecture. Compare migration rows, table definitions, and indexes to `seed_kiro_db.py` and its focused unit test. If only the CLI version changes and the schema is identical, update the seed's verification annotation and test expectations without rewriting the schema. If the schema changes, update the seed and test the auth-injection path against the new database before accepting the image.

**Alternative considered:** assume the previous 2.27.1 seed remains valid because the patch release is small. That can silently break credential injection if upstream migrations changed independently of the apparent version size.

### Gate acceptance on the upstream behavior and credential review

Review the release diff for behavior that intersects with Ghostship, including queued message handoff after cancellation/restart, shell safety changes, MCP/KAS retry behavior, and dashboard reconnect behavior. For the upstream local sign-in token delivery change, trace whether any Ghostship composition, MCP configuration, or launch path enables app backends or exposes the token. Keep app/token exposure out of scope; if the trust boundary cannot be demonstrated safe for the shipped configurations, hold the pin and resolve that design before implementation.

**Alternative considered:** accept all upstream features with the base image. That would implicitly expand Ghostship's credential surface without an explicit product decision.

### Validate with disposable crews and preserve existing volumes

Build using the verified digest and exercise a fresh crew through authentication, dispatch, pickup, stop/wake, and a subsequent task. Validate the release on Corsair and Carrier using disposable crew data where applicable. Do not nuke or recreate existing crews. Record that existing containers retain their original image until their normal lifecycle replaces them.

**Alternative considered:** recreate the fleet to force immediate adoption. This would be destructive to persistent crew state and is unnecessary for a base-image default change.

### Roll back the default pin as a matched image-and-seed pair

If validation fails, restore the prior 0.13.0 digest and its matching seed state, rebuild, and verify authentication on a disposable fresh crew. Do not point an older image at a home volume that has already been opened or migrated by 0.13.1 unless backward compatibility is explicitly verified. Deployment remains subject to the normal deployment approval.

## Risks / Trade-offs

- **The published tag or architecture manifests do not match the expected release** → Verify the registry index and each supported platform manifest before editing either default; stop if the release cannot be tied to immutable digests.
- **A migration or schema change is missed** → Inspect the initialized database, compare tables/indexes and migration rows, and run focused seed plus auth-injection tests against the candidate image.
- **Token delivery expands credential access** → Inspect shipped compositions and runtime configuration; do not enable app integrations, and block adoption if local sign-in token handling cannot be shown to remain within the intended trust boundary.
- **A new CLI writes state an older image cannot read** → Keep existing crews untouched, use disposable data for rollout/rollback checks, and restore the old image only with a compatible seed/database state.
- **Backend credentials or upstream service behavior prevent a live smoke test** → Record which backends were exercised and treat unverified backends as a release limitation rather than inferring compatibility from image inspection.

## Migration Plan

1. Verify the stable 0.13.1 image index, supported architecture manifests, bundled Kiro CLI, migration rows, database schema, and release diff; settle the credential trust-boundary review.
2. Update the admission pin and shipped default together. Refresh `seed_kiro_db.py` and its focused tests only as indicated by the actual schema comparison.
3. Update `dependencies.yaml`, runtime documentation, the changelog, and this capability's main spec upon assimilation with verified versions and evidence. Do not add standalone dependency-review documents.
4. Build and validate the image on Corsair and Carrier using fresh/disposable crews. Check login/authentication, a task dispatch and pickup, and stop/wake followed by another task.
5. Record outcomes against TRN-363. Leave existing crew containers and home volumes intact.

If any release gate fails, restore the prior image digest and matching seed, rebuild, and verify authentication on disposable data. No automatic fleet recreation or deployment is part of this plan.
