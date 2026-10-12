# Design

## Context

`ghostship.conf.example` has grown to 63 variables across four categories:

1. **Hardcode candidates** — values fixed in the standard install that should never be
   env-overridable (`GA_CREW_AGENT` as KiroCrew's internal agent name, `TRANSPORT_DATA_DIR`,
   `GA_ENABLE_SECURITY_HEADERS`, `GA_TLS_MIN_VERSION`, `GA_PREWARM_ENABLED`,
   `GA_PREWARM_TTL_SECS`, `GA_SUBAGENT_MAX_TURNS`, `GA_COMPOSE_RETRY_ATTEMPTS`,
   `GA_COMPOSE_RETRY_DELAY_SECS`).
2. **Redundant backend vars** — `GA_CREW_ACP_BACKEND` + `GA_AGENT_BACKENDS` both exist
   because Ghostship builds multi-toolchain images, but KiroCrew is strictly one backend
   per gateway (confirmed from 0.9.0rc4 source: `acp_backend` is a plain `str`, no
   per-session override, no multi-backend roadmap). Two vars to express one concept.
3. **Broken wiring** — `GA_ORDERS_DIR` and TLS cert/key vars reach compose as env vars
   but the host paths are never mounted, so the transport can't read them.
4. **Overexposed tuning knobs** — rate limits, memory pressure thresholds, dashboard port
   ranges, and other knobs operators should never touch in a normal install.

## Goals / Non-Goals

**Goals:**
- Hardcode 9 vars that should never have been configurable
- Consolidate `GA_CREW_ACP_BACKEND` + `GA_AGENT_BACKENDS` → `GA_CREW_AGENT`
- Fix `GA_ORDERS_DIR` and TLS cert/key volume mounts
- Prune `ghostship.conf.example` to ~30 genuine operator vars
- Maintain backward compatibility via deprecated aliases for one release

**Non-Goals:**
- Changing any runtime behaviour beyond the volume mount fixes and backend consolidation
- Adding new config vars
- Formal constants file extraction (may follow separately)

## Decisions

### D1 — Hardcode 9 vars

Remove from `Config` dataclass and `Config.from_env()`. Replace usages with literals or
module-level constants. Remove from compose template.

| Var | New form |
|-----|---------|
| `GA_CREW_AGENT` (KiroCrew internal name) | `_KC_AGENT_NAME = "kiro"` constant |
| `TRANSPORT_DATA_DIR` | `"/data"` literal at usage sites |
| `GA_ENABLE_SECURITY_HEADERS` | remove field; always `True` in SecurityHeadersMiddleware |
| `GA_TLS_MIN_VERSION` | `_TLS_MIN_VERSION = "1.2"` constant in server.py |
| `GA_PREWARM_ENABLED` | remove field; `_prewarm_crew` always runs when called |
| `GA_PREWARM_TTL_SECS` | `_PREWARM_TTL_SECS = 300` constant in lifecycle.py |
| `GA_SUBAGENT_MAX_TURNS` | `_SUBAGENT_MAX_TURNS = 200` constant in lifecycle.py |
| `GA_COMPOSE_RETRY_ATTEMPTS` | `_COMPOSE_RETRY_ATTEMPTS = 3` in install.sh |
| `GA_COMPOSE_RETRY_DELAY_SECS` | `_COMPOSE_RETRY_DELAY_SECS = 2` in install.sh |

**Note:** `GA_PREWARM_ENABLED=False` is the current default and the correct behaviour
(prewarm is implicit since TRN-194). Hardcoding removes the disabled gate — prewarm now
always fires when triggered. Callers already guard with `if GA_PREWARM_ENABLED` — those
guards are removed.

### D2 — GA_CREW_AGENT replaces GA_CREW_ACP_BACKEND + GA_AGENT_BACKENDS

KiroCrew uses exactly one backend per gateway instance (`acp_backend: str`). The
Ghostship split (build-time list vs runtime default) is unnecessary complexity.

**New behaviour:**
- `GA_CREW_AGENT=kiro` (default) — build kiro toolchain, crews use kiro
- `GA_CREW_AGENT=claude` — build claude toolchain, crews use claude
- `GA_CREW_AGENT=claude,codex` — build both toolchains, first entry (claude) is the
  runtime default; advanced use, not in conf.example

**In install.sh:**
- Parse `GA_CREW_AGENT` as comma-separated list for `AGENT_TOOLCHAINS` (replaces
  `GA_AGENT_BACKENDS`)
- First entry becomes `GA_CREW_ACP_BACKEND` passed to compose (replaces the old var)
- Deprecated alias handling: if `GA_AGENT_BACKENDS` or `GA_CREW_ACP_BACKEND` are set,
  warn and map to `GA_CREW_AGENT` for this run

**In transport:**
- `Config.ga_crew_agent` replaces both `ga_crew_acp_backend` and `ga_agent_backends`
- `from_env()` reads `GA_CREW_AGENT` first; falls back to `GA_CREW_ACP_BACKEND` with
  deprecation log; ignores `GA_AGENT_BACKENDS` (install.sh handles that)
- The runtime default backend is `ga_crew_agent.split(",")[0]`

### D3 — GA_ORDERS_DIR gets a conditional volume mount

When `GA_ORDERS_DIR` is set, `install.sh` adds `- ${GA_ORDERS_DIR}:/mnt/orders:ro` to
the compose volume block and rewrites the env var to the fixed container path `/mnt/orders`.
Require absolute path; warn if path doesn't exist at install time.

### D4 — TLS cert/key get a conditional volume mount

When both TLS vars are set, mount their parent directory as `/mnt/tls:ro` and rewrite
both vars to container-side paths. Require same parent directory; error if they differ.

### D5 — Fix lifecycle.py comment only; no code floor

The "Both TTLs floor at one hour" comment is wrong. Fix the comment; don't add a floor
to `_TASK_TIMESTAMP_TTL_SECS` — that's a behaviour change out of scope here.

### D6 — Pruned vars stay in config.py but leave conf.example

Advanced vars (`PODMAN_SOCKET`, `KC_IMAGE`, `KC_BASE_IMAGE`, `GA_MACHINE_NAME`,
`GA_MIN_FREE_MEM_GB`, `GA_SUBAGENT_TIMEOUT_SECS`, memory pressure vars,
`GA_DASHBOARD_PORT_RANGE_START`, `GA_RATE_LIMIT_*`) remain in `config.py` and
`docs/configuration.md` (advanced section). They are removed from `ghostship.conf.example`
only. Operators who need them can set them; they're just no longer in the main operator
file.

## Risks

- **`GA_CREW_AGENT` name collision** — the old `GA_CREW_AGENT` wrote `"kiro"` into
  `config.local.json`. The hardcoding step (D1) must land before the rename step (D2)
  in the same commit — no intermediate state where both meanings coexist.
- **`GA_PREWARM_ENABLED` removal** — currently defaults to `False` so prewarm is off
  everywhere. Hardcoding "always run when called" means the implicit triggers added by
  TRN-194 (`supply`, `schedule`) now actually fire. This is intentional and the correct
  behaviour, but worth noting.
- **Deprecated alias window** — `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS` must
  continue to work (with a deprecation warning) for one release to avoid breaking
  existing installs.
