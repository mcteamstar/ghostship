## 1. VERSION File and Python Constant

- [x] 1.1 Create `VERSION` file at repo root containing `0.1.0`
- [x] 1.2 Add version-reading utility in `transport/server.py` that reads `VERSION` at startup into a module-level constant, defaulting to `0.0.0-dev` if file is missing

## 2. Crew Image Label

- [x] 2.1 Add `ARG VERSION=0.0.0-dev` and `LABEL org.ghostship.version=$VERSION` to `crews/spec-ops/Containerfile`
- [x] 2.2 Update `install.sh` build command to pass `--build-arg VERSION=$(cat VERSION)` when building the crew image

## 3. Transport Version Endpoint and Resource

- [x] 3.1 Add `GET /version` HTTP route on the MCP port returning `{"transport": "<semver>"}` — unauthenticated
- [x] 3.2 Register `transport://version` MCP resource returning transport version and per-crew `crew_image_version` from the registry

## 4. Registry and Launch Integration

- [x] 4.1 In `launch()`, after container start, read `org.ghostship.version` label via `podman inspect` and store as `crew_image_version` in the registry entry (default `"unknown"` if label absent)
- [x] 4.2 In `crews()`, include `crew_image_version` field in each entry (default `"unknown"` for crews without the field)

## 5. Tests and Validation

- [x] 5.1 Add unit test: version-reading utility returns file content when present, `0.0.0-dev` when absent
- [x] 5.2 Add unit test: `GET /version` returns correct JSON structure
- [x] 5.3 Add integration test: `crews()` output includes `crew_image_version` field
- [x] 5.4 Verify Containerfile builds successfully with the new ARG/LABEL

## 6. Documentation

- [x] 6.1 Document `VERSION` file convention and release tagging (`v<semver>` on main) in README or a RELEASING.md
