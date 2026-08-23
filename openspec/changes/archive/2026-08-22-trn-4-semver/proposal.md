## Why

Ghostship is a monorepo shipping three versioned things that can drift
independently in a real deployment:

- **Transport** (`ga-transport`) — the MCP server and orchestration layer
- **Crew image** (`kirocrew`) — the Ghost Academy curriculum: agent personas,
  skills, steering documents baked into the container image
- **Ghostship runtime** — the combination of the two; the version an operator
  is actually running

Right now there's no way to answer "what version is this?" from the MCP API,
from inside a crew container, or from a git tag. This makes it impossible to:
- Know if a deployed instance is up to date
- Reference a specific release in a bug report
- Build a proper release pipeline later
- Track which crew image curriculum is loaded in a running crew

This is a stub only — capturing the direction for a future design pass.

## What Changes (sketch, not final)

- **`VERSION` file** — a single `VERSION` file at the repo root containing the
  current semver string (e.g. `0.4.0`). Source of truth for all other surfaces.
  Updated manually (or by a release script) on each release.

- **Crew image label** — `LABEL version=<curriculum-version>` in the
  `Containerfile`, sourced from `VERSION` at build time. Accessible via
  `podman inspect` or inside the container as an OCI label. Lets the transport
  know what curriculum version a running crew was built with.

- **Transport version endpoint** — a `GET /version` route (or MCP resource
  `transport://version`) returning JSON with:
  - `transport`: semver of the transport process
  - `crew_image`: semver of the crew image (read from the OCI label at crew
    launch time, stored in registry)
  - `ghostship`: combined runtime version (same as transport, or a separate
    field if curriculum and transport versions diverge)

- **`crews()` version field** — include `crew_image_version` per crew entry so
  the Admiral can see at a glance if any crew is running a stale image.

- **Git tags** — release tagging convention: `v<semver>` on main. Not
  automated here, just documented as the release convention.

## Decisions

- **One shared `VERSION` file** — transport and crew image share a single
  version. They always ship together as a monorepo; independent versioning adds
  complexity for no benefit at this stage.

## Open questions for the real design pass

- Where does the crew image version get written into the registry — at launch,
  or lazily on first pickup?
- Does `install.sh` need updating to pass `--build-arg VERSION=...` to podman
  build so the label is stamped correctly?

## Capabilities

### Modified Capabilities
- `mcp-server`: new `transport://version` resource or `GET /version` route —
  not yet specced, pending the real design pass.
- `crew-lifecycle`: `crews()` gains a `crew_image_version` field — not yet
  specced.

## Impact

- `VERSION` (new file at repo root)
- `crews/spec-ops/Containerfile` — add `LABEL` instruction
- `transport/server.py` — version endpoint, registry storage, `crews()` field
- `install.sh` — potentially pass `--build-arg VERSION=...` to podman build
- Not yet scoped: release tagging automation, changelog generation
