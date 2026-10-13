# Proposal

**Plane ticket:** TRN-231

## Why

The default ghostship install binds on `0.0.0.0` with no API key and only emits a warning. Any device that can reach the host can call every MCP tool. `GA_REQUIRE_API_KEY` currently defaults to `warn`, which was addressed in TRN-207 (network-exposure-defaults). This change promotes it from a warning to an enforced error: remote installs without `GA_API_KEY` abort; local installs (loopback bind) require no key. An explicit `off` override is available for operators who place their own auth layer in front (Tailscale, VPN, reverse proxy).

## What Changes

- **`GA_REQUIRE_API_KEY` default changes from `warn` to `error`** — install.sh already supports `error` mode; this makes it the default.
- **install.sh**: the existing check at install time (line 831) already aborts on `error` — no code change needed there. What changes: the default value written into `ghostship.conf` changes from `warn` to `error`, and the comment is updated.
- **Transport startup gate**: `transport/server.py` reads `GA_REQUIRE_API_KEY` at startup (line 544). Currently `warn` logs a warning. Change the default to `error` so the transport also refuses to start on a non-loopback bind without `GA_API_KEY`, unless `GA_REQUIRE_API_KEY=off`.
- **Loopback exemption**: when `HOST=127.0.0.1` (or unset, which defaults to loopback), the check is skipped entirely — no API key required for local installs.
- **Documentation**: update `docs/configuration.md` and `config/ghostship.conf.example` to reflect the new default and document the `off` escape hatch.
- **Consider**: remove `warn` mode entirely — it was a transitional state. If operators have `warn` set explicitly they'd need to update, but `warn` has no valid use case now that `off` exists for intentional unauthenticated access.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `installation`: add requirement that remote (non-loopback) installs without `GA_API_KEY` are rejected at install time and transport startup unless `GA_REQUIRE_API_KEY=off`.
- `config-file`: update `GA_REQUIRE_API_KEY` default from `warn` to `error`; document `off` as the explicit override for proxy-protected deployments.

## Impact

- `scripts/install.sh` — change default value of `GA_REQUIRE_API_KEY` written to conf
- `transport/server.py` — change startup enforcement default
- `config/ghostship.conf.example` — update default and comment
- `docs/configuration.md` — update reference table entry
