# Initial dependency review — 2026-11-08

Command: `python3 scripts/dependency_check.py check` (stable candidates only). The inventory validated 40 components and 35 extracted declarations. All queried upstream requests returned a result; components without a direct version source are explicitly unknown because the check does not inspect built images, the CI runner or the host. The [KiroCrew release page](https://github.com/kirodotdev/KiroCrew/releases) reports `v0.12.0`; the release is a candidate for the digest-pinned image, not proof of the image's resolved contents.

Every component remains compatibility `unknown` unless marked `unsupported`. A candidate is not approval to change a pin, and a matching package version does not establish integration compatibility. The check did not inspect installed image contents, query advisories, fetch/re-hash the NodeSource script, or resolve image tags to immutable digests. The `.agents` commit is the current remote `main` head; the image's installed commit remains unknown.

| Component | Declared input | Stable upstream result | Compatibility and review outcome |
|---|---|---|---|
| `kirocrew-image` | GHCR digest `d7eeab…def5d0f` | KiroCrew `v0.12.0` | Unknown; release-to-image digest association not inspected |
| `kiro-cli` | Inherited from KiroCrew | Parent release `v0.12.0` | Unknown; installed CLI version not inspected |
| `codex-acp` | `2.5.0` | `2.5.0` | Unknown; current pin has known model catalogue mismatch |
| `codex-cli` | Supplied by `codex-acp` | Parent adapter `2.5.0` | **Unsupported**; bundled CLI version and advertised-model coverage unverified |
| `claude-agent-acp` | `0.79.0` | `0.101.0` | Unknown; adapter/CLI smoke test not run |
| `claude-code` | `2.1.293` | `2.1.319` | Unknown; adapter/CLI smoke test not run |
| `openspec-cli` | `1.14.3` | `1.16.1` | Unknown; generated skills not checked against candidate |
| `shared-agent-assets` | Git branch `main` | Commit `3ca5a8822a96` (2026-11-07) | Unknown; local image commit not inspected |
| `openspec-skills` | Derived from CLI and shared assets | Parent CLI candidate `1.16.1` | Unknown; installed skill metadata not inspected |
| `nodejs-24` | Node 24 stream; setup checksum declared | `24.22.2` | Unknown; setup script was not fetched or re-hashed |
| `python-transport-image` | `python:3.12.10-slim` | `3.12.16-slim` | Unknown; candidate tag digest not resolved |
| `python-worker-image` | `python:3.12.10-slim` | `3.12.16-slim` | Unknown; candidate tag digest not resolved |
| `python-radar-image` | `python:3.12-slim` | `3.12.16-slim` | Unknown; floating tag resolution not inspected |
| `caddy-image` | `docker.io/caddy:2` | `2.11.9` | Unknown; major tag digest not resolved |
| `podman-host` | README minimum `>=4.4` | `v6.1.4` | Unknown; maintainer host version not inspected |
| `podman-compose-host` | Unpinned host prerequisite | `v1.6.0` | Unknown; maintainer host version not inspected |
| `action-checkout` | Workflow ref `v7` | `v7.0.1` | Unknown; release candidate is not a workflow compatibility check |
| `action-setup-python` | Workflow ref `v7` | `v7.1.0` | Unknown; workflow not exercised against candidate |
| `ci-python-runtime` | Python `3.12` stream | Unknown | Runner-selected patch version not inspected |
| `action-upload-artifact` | Workflow ref `v7` | `v7.0.2` | Unknown; workflow not exercised against candidate |
| `os-base-admission` | `mailutils`, `msmtp`, `msmtp-mta` group | Unknown | Package versions require a built-image inspection |
| `os-worker` | `git` group | Unknown | Package version requires a built-image inspection |
| `os-spec-ops` | `ca-certificates`, `curl`, `git`, `nodejs` group | Unknown | Package versions require a built-image inspection |
| `os-kirocrew-inherited` | Inherited from KiroCrew | Unknown | Image package list not inspected |
| `os-python-inherited` | Inherited from Python images | Unknown | Image package lists not inspected |
| `transport-mcp` | `==2.2.0` | `2.3.0` | Unknown; exact pin retained |
| `transport-httpx2` | `==2.12.0` | `2.16.0` | Unknown; exact pin retained |
| `transport-websockets` | `>=13.0,<15.0` | `17.4` | Unknown; candidate is outside the declared range |
| `transport-croniter` | `==6.2.4` | `6.2.4` | Unknown; matching candidate is not installed-version evidence |
| `transport-pyyaml` | `>=6.0,<7.0` | `6.0.3` | Unknown; no runtime resolution inspected |
| `transport-starlette` | `>=1.0.1,<2.0.0` | `1.10.0` | Unknown; no integration evidence for candidate |
| `transport-uvicorn` | `>=0.31.1,<1.0.0` | `0.54.0` | Unknown; no integration evidence for candidate |
| `transport-pytest` | `>=8.0.0,<9.0.0` | `9.2.0` | Unknown; candidate is outside the declared range |
| `transport-pytest-xdist` | `>=3.5.0,<4.0.0` | `3.8.0` | Unknown; no test suite run against candidate |
| `transport-pytest-cov` | `>=5.0.0,<7.0.0` | `7.1.0` | Unknown; candidate is outside the declared range |
| `transport-cryptography` | `>=43.0.1,<51.0.0` | `50.0.2` | Unknown; no runtime resolution inspected |
| `radar-starlette` | `>=1.0.1,<2.0.0` | `1.10.0` | Unknown; no Radar integration evidence for candidate |
| `radar-httpx2` | `==2.12.0` | `2.16.0` | Unknown; exact pin retained |
| `radar-uvicorn` | `==0.34.2` | `0.54.0` | Unknown; candidate differs from exact pin |
| `cryptography-base` | `==50.0.1` | `50.0.2` | Unknown; exact pin retained |

The follow-up date for every reviewed component is **2026-12-08**. Unknown image, host, derived-version and compatibility results remain explicit in `config/dependencies.yaml`; no dependency pin or runtime configuration was changed by this report.
