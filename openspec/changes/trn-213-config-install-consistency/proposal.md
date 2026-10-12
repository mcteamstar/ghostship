## Why

`ghostship.conf.example` has grown to 63 documented variables. The bloat falls into
three categories: internal constants that should never be configurable, broken vars whose
wiring is missing, and two redundant backend vars that expose KiroCrew internals instead
of a clear operator concept.

This change does four things:

1. **Hardcode** 9 vars that should never have been configurable — eliminate them from
   `config.py` and compose entirely.
2. **Consolidate** `GA_CREW_ACP_BACKEND` + `GA_AGENT_BACKENDS` into a single
   `GA_CREW_AGENT` var — clear name, one concept, replaces both.
3. **Fix** broken wiring for `GA_ORDERS_DIR` and TLS cert/key vars (missing volume mounts).
4. **Prune** `ghostship.conf.example` to ~30 genuine operator vars; move the rest to
   `docs/configuration.md` advanced section only.

## What Changes

### 1. Hardcoded eliminations (removed from config.py and compose)

These vars are removed from `Config`, `Config.from_env()`, and `compose.yml`. Their
values become Python literals or module-level constants:

| Var | Hardcoded to |
|-----|-------------|
| `GA_CREW_AGENT` (old meaning) | `"kiro"` in lifecycle.py / server.py |
| `TRANSPORT_DATA_DIR` | `"/data"` literal |
| `GA_ENABLE_SECURITY_HEADERS` | always `True` |
| `GA_TLS_MIN_VERSION` | `"1.2"` literal |
| `GA_PREWARM_ENABLED` | gate removed; prewarm always fires when triggered |
| `GA_PREWARM_TTL_SECS` | `300` module-level constant in lifecycle.py |
| `GA_SUBAGENT_MAX_TURNS` | `200` module-level constant |
| `GA_COMPOSE_RETRY_ATTEMPTS` | `3` constant in install.sh |
| `GA_COMPOSE_RETRY_DELAY_SECS` | `2` constant in install.sh |

### 2. GA_CREW_AGENT — single backend var (rename + consolidation)

`GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS` are replaced by a single `GA_CREW_AGENT`.

- **`GA_CREW_AGENT`** — which agent backend to build and run. Values: `kiro` (default),
  `claude`, `codex`, `opencode`. Install.sh builds the toolchain for the specified
  backend; the transport accepts login and launches crews for that backend.
- Comma-separated list accepted (e.g. `GA_CREW_AGENT=claude,codex`) for multi-toolchain
  builds; first entry is the runtime default. Not documented in conf.example — advanced
  use only.
- `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS` become deprecated aliases: install.sh
  maps them to `GA_CREW_AGENT` with a warning for one release cycle.

### 3. Fixed — broken vars that remain after pruning

- `GA_ORDERS_DIR` — add conditional volume mount in install.sh (`/mnt/orders:ro`),
  rewrite env var to container path.
- `GA_TLS_CERTFILE` / `GA_TLS_KEYFILE` — add conditional volume mount (`/mnt/tls:ro`),
  require same parent directory, rewrite paths to container-side basenames.
- Fix `lifecycle.py` comment: "Both TTLs floor at one hour" — only warm-marker TTL is
  floored; `_TASK_TIMESTAMP_TTL_SECS` has no floor.

### 4. Pruned from ghostship.conf.example

After hardcoding and consolidation, `ghostship.conf.example` is pruned to ~30 genuine
operator vars. The following move to `docs/configuration.md` advanced section only
(remain in config.py, just not in the example file):

- `PODMAN_SOCKET`, `KC_IMAGE`, `KC_BASE_IMAGE` — dev/fork use only
- `GA_MACHINE_NAME` — only needed when running two ghostship instances side-by-side
- `GA_MIN_FREE_MEM_GB` — escape hatch for constrained hosts
- `GA_SUBAGENT_TIMEOUT_SECS` — long-running task tuning
- `GA_SPAWN_MIN_MEMORY_GB`, `GA_RESOURCE_PRESSURE_GB`, `GA_RESOURCE_CRITICAL_GB`,
  `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` — KiroCrew memory gate tuning
- `GA_DASHBOARD_PORT_RANGE_START` — multi-tenant port conflict resolution
- `GA_RATE_LIMIT_*` (5 vars) — emergency rate limit tuning

## Capabilities

### Modified Capabilities

- `installation`, `config-file`

## Impact

`transport/config.py`, `transport/lifecycle.py`, `transport/server.py`,
`scripts/install.sh`, `docs/configuration.md`, `config/ghostship.conf.example`.
