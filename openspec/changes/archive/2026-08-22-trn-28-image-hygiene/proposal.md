# Proposal: trn-28-image-hygiene

## Why

Both Containerfiles use floating base image references that silently drift on rebuild, and `install.sh` has several reliability gaps identified in the post-0.3.x code review.

1. **Floating base images** — `python:3.12-slim` and `ghcr.io/kirodotdev/kirocrew:stable` have no digest pins. A rebuild on a different day can silently pull a different image.

2. **NodeSource curl-pipe-to-bash** — the Node.js install in the crew Containerfile uses `curl | bash` with no integrity check and no patch-version pin.

3. **install.sh reliability gaps** — three targeted issues:
   - `podman machine ssh` calls on macOS have no error handling; a malformed `GUEST_UID` produces silent failures downstream
   - `sleep 3` health check is not a real readiness probe
   - `source "$CONFIG_FILE"` is undocumented arbitrary code execution

## What Changes

- Pin `transport/Containerfile` to `python:3.12.x-slim` (current patch version)
- `crews/spec-ops/Containerfile`: add a comment documenting the `stable` tag fragility; pin to a versioned tag when upstream publishes one
- Replace NodeSource curl-pipe-to-bash with a safer install method or add an integrity check
- Add `|| { echo "...; exit 1; }` error handling to `podman machine ssh` calls in `install.sh`
- Replace `sleep 3 && podman ps` with a bounded retry readiness probe (curl the MCP endpoint)
- Add a comment to `source "$CONFIG_FILE"` documenting the arbitrary-code-execution trust assumption

## Capabilities

### Modified Capabilities

- `installation` — install.sh reliability: proper error handling, real readiness probe, documented config trust model

## Impact

- `transport/Containerfile` — base image pin
- `crews/spec-ops/Containerfile` — base image comment, Node.js install hardening
- `install.sh` — error handling, readiness probe, config source comment
- No behavior change for end users
