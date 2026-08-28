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
