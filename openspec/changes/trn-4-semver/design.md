## Context

See proposal.md — Why. Currently neither the transport nor any crew container
exposes a version. The transport is a single-file Python MCP server; the crew
image is built via `crews/spec-ops/Containerfile`.

## Goals / Non-Goals

**Goals:**
- Single source-of-truth `VERSION` file at the repo root
- Transport reads it at startup and exposes it via MCP resource + HTTP endpoint
- Crew image stamps the version as an OCI label at build time
- Transport reads the OCI label at crew launch, stores it in the registry
- `crews()` output includes `crew_image_version` per entry

**Non-Goals:**
- Automated version bumping or changelog generation (future release tooling)
- Independent versioning of transport vs crew image (one shared version for now)
- Git tag automation (documented convention only, not enforced by code)
- Pre-release/build-metadata parsing beyond standard semver acceptance

## Decisions

### D1: Single `VERSION` file shared by transport and image

**Choice:** One plain-text `VERSION` file at repo root containing e.g. `0.4.0\n`.

**Rationale:** Transport and crew image ship together from the same monorepo and
are released in lockstep. Two separate version files would immediately diverge
without benefit. A file (vs a Python constant) is trivially readable by shell
scripts, `Containerfile ARG`, and CI — no import machinery needed.

**Alternatives considered:**
- `pyproject.toml [project].version` — requires a TOML parser to read from
  shell or Containerfile; adds coupling to Python packaging we don't ship.
- Git-describe-based version — requires `.git` at runtime, breaks in containers.

### D2: OCI label `org.ghostship.version` for crew images

**Choice:** Add `LABEL org.ghostship.version=$VERSION` to the Containerfile,
sourced via `ARG VERSION` defaulting to `0.0.0-dev`.

**Rationale:** OCI labels are inspectable without starting the container
(`podman inspect`), and the transport can read them from a running container
via `podman inspect --format '{{.Config.Labels}}'`. The `org.ghostship.*`
namespace avoids collision with standard OCI annotations.

**Alternatives considered:**
- Writing version to a file inside the image — requires exec-ing into the
  container to read it, which is slower and fails on stopped containers.
- Using the standard `org.opencontainers.image.version` label — acceptable but
  less specific; we may use both in future for registry metadata.

### D3: Transport reads `VERSION` at startup, not per-request

**Choice:** Read the file once at process startup into an in-memory constant.

**Rationale:** The version never changes during a running process. File I/O per
request is wasteful. A restart picks up a new version naturally.

### D4: `/version` endpoint is unauthenticated

**Choice:** The HTTP `GET /version` route does NOT require `GA_API_KEY`.

**Rationale:** Version information is not sensitive and is commonly used by
monitoring, load balancers, and health checks that do not carry credentials.
The MCP resource `transport://version` still requires normal MCP auth.

### D5: Registry stores `crew_image_version` at launch

**Choice:** Read the label immediately after container creation (before gateway
readiness check) and write it into the crew's registry entry.

**Rationale:** At launch the container exists and can be inspected. Reading
lazily on `crews()` would add a `podman inspect` per crew on every list call,
which is O(n) and slow. A one-time write at launch is O(1) at query time.

## Risks / Trade-offs

- **[Risk] `podman inspect` may be slow on some hosts** → Mitigation: it runs
  once per launch (D5), not per `crews()` call.
- **[Risk] Existing crews launched before this change have no version in
  registry** → Mitigation: `crews()` defaults missing field to `"unknown"`;
  next `launch` or re-launch populates it.
- **[Risk] VERSION file accidentally deleted** → Mitigation: transport defaults
  to `"0.0.0-dev"` if the file is absent; CI can lint for its presence.

## Migration Plan

1. Add `VERSION` file containing `0.1.0` (first formal version).
2. Update `Containerfile` to accept `ARG VERSION=0.0.0-dev` and add the label.
3. Update `install.sh` to pass `--build-arg VERSION=$(cat VERSION)` to the
   build command.
4. Add version-reading logic to `transport/server.py` startup.
5. Register `transport://version` resource and `GET /version` route.
6. In `launch()`, after container start, read the label and store in registry.
7. In `crews()`, include the stored `crew_image_version` field.

Rollback: revert the commits; existing running crews are unaffected since the
field is additive and `"unknown"` is handled gracefully.
