# Proposal

## Why

`podman compose up` in `install.sh` has no retry logic. On macOS, the kernel's ephemeral port range overlaps the dashboard port space and a transient port conflict — a port grabbed momentarily by another process — causes an immediate hard install failure. The port is typically released within a second or two, so a short retry loop recovers without operator intervention.

(The companion fix — reducing `GA_DASHBOARD_PORT_RANGE_SIZE` from 1024 to 64 — was already hotfixed in commit `660ae48`. This change adds the retry logic that was the second half of TRN-227.)

## What Changes

- `scripts/install.sh`: wrap the `podman compose up` invocation in a retry loop — up to 3 attempts with a 2-second sleep between them. On final failure, surface the compose error and exit non-zero.
- `docs/configuration.md` and `config/ghostship.conf.example`: document `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` so operators can tune or disable the retry.
- Unit test: add a test covering the retry loop logic (stub compose to fail N times then succeed).

## Capabilities

### New Capabilities

_(none — this adds a requirement to an existing capability)_

### Modified Capabilities

- `installation`: add a requirement that `install.sh` retries `compose up` on failure before giving up.

## Impact

- `scripts/install.sh` — compose up invocation only (line ~1068)
- `docs/configuration.md` — new config vars section entry
- `config/ghostship.conf.example` — two new commented-out vars
- `tests/integration/test_install_config.sh` or a new unit test — retry behaviour
