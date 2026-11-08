# Releasing

## Version Scheme

Ghostship uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).
The current version lives in the `VERSION` file at the repository root.

## Single Source of Truth

The `VERSION` file is the single source of truth for the transport process and
the crew image. Both ship together from this monorepo in lockstep — there is no
independent versioning of transport vs crew image at this stage.

Consumers:

| Surface                    | How it reads `VERSION`                                           |
|----------------------------|------------------------------------------------------------------|
| Transport process          | Reads at startup into `TRANSPORT_VERSION` constant               |
| Crew image (OCI label)     | `--build-arg VERSION=$(cat VERSION)` at `podman build` time      |
| `GET /version`             | Returns `{"transport": "<semver>"}` (unauthenticated)            |
| `transport://version`      | MCP resource with transport + per-crew image versions            |
| `crews()` tool             | Includes `crew_image_version` per entry from registry            |
| `.claude-plugin/plugin.json` | Agent Plugins manifest `version` field — update by hand         |
| `.claude-plugin/.claude-plugin/plugin.json` | Claude Code plugin manifest `version` field — update by hand |

## Release Process

1. **Bump the version**: edit `VERSION` to the new semver string (no leading `v`).
2. **Bump the plugin manifests**: set `version` to the same string in both
   `.claude-plugin/plugin.json` and `.claude-plugin/.claude-plugin/plugin.json`.
   The `release-gate` workflow fails the PR into `main` if either drifts from
   `VERSION`.
3. **Commit**: `git commit -am "release: v<semver>"`
4. **Tag**: `git tag v<semver>` on the release commit on `main`.
5. **Build**: `install.sh` automatically passes the version to `podman build`.

## Dependency review before release

Before each release, run `python3 scripts/dependency_check.py validate` and
`python3 scripts/dependency_check.py check`. Resolve declaration drift and
record each component's outcome, evidence and next review date in
`config/dependencies.yaml`. A lookup candidate is not approval to upgrade or
evidence of compatibility. Review security advisories and upstream
compatibility warnings as soon as they are found, even between releases.

For every dependency changed since the previous release, complete the
applicable checks:

| Upgrade category | Acceptance check | Rollback |
|---|---|---|
| ACP adapter and supplied CLI | Confirm the KiroCrew supported adapter range; exercise login/authentication, model discovery and a fresh crew turn that records the actual selected model. Codex remains unsupported until its model catalogue gap is resolved and this smoke test passes. | Restore the prior adapter pin and image; rebuild and verify the prior backend before release. |
| KiroCrew base image and Kiro CLI | Inspect the built image's actual image/version and Kiro CLI; compare the SQLite migration count and schema with `crews/_base/graduation/seed_kiro_db.py`; run the auth injection smoke test. | Restore the previous image digest and seed script together, rebuild, and verify authentication on a fresh crew. |
| OpenSpec CLI and generated skills | Check the installed CLI against the generated skill `metadata.generatedBy` and run the documented OpenSpec commands in a fresh crew. | Restore the previous CLI pin and matching shared skill source/ref, rebuild, and verify the OpenSpec commands. |
| Node.js and NodeSource setup script | Verify the fetched setup script SHA-256 against the declared checksum, build the spec-ops image, and record the resolved Node version. | Restore the prior Node stream and checksum as a pair, then rebuild and verify the prior version. |
| Python runtime or package | Run the affected transport or Radar tests, rebuild the affected image and inspect the resolved package versions. | Restore the prior image tag and package constraint, rebuild, and rerun the affected tests. |
| Shared `.agents` source/ref or OS package group | Inspect the resolved commit or installed package list in the built image; run a fresh-crew launch smoke test for changed assets. | Restore the prior ref or package declarations and rebuild the image. |
| GitHub Actions, Podman or podman-compose | Exercise the affected workflow or host install/build path on the supported environment. Record the installed host version where relevant. | Restore the prior action ref or host-tool version and rerun the affected workflow/build check. |

After the applicable checks pass, rebuild affected images and confirm a fresh
crew adopts the recorded versions. Preserve the previous declarations, image
digest and review evidence so the rollback can be performed. Deployment still
requires the normal explicit approval; reporting and review do not deploy or
modify running crews.

## Git Tag Convention

Tags follow the pattern `v<MAJOR>.<MINOR>.<PATCH>` on `main`:

```
v0.1.0
v0.2.0
v1.0.0
```

Pre-release builds (from feature branches or CI) use `0.0.0-dev` as the
default when the `VERSION` file is not present or not passed as a build arg.

## Fallback Behavior

- If `VERSION` is missing at transport startup → defaults to `"0.0.0-dev"`
- If a crew image lacks the `org.ghostship.version` OCI label → stored as `"unknown"`
- Crews launched before version tracking have `crew_image_version: "unknown"`
