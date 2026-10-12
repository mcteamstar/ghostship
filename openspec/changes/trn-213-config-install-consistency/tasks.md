# Tasks

## 1. Hardcode 7 eliminated vars (transport/config.py, lifecycle.py, server.py)

- [x] 1.1 In `transport/config.py`, remove the following fields from the `Config` dataclass
      and their corresponding `from_env()` lines: `ga_crew_agent` (old meaning),
      `transport_data_dir`, `ga_enable_security_headers`, `ga_tls_min_version`,
      `ga_prewarm_enabled`, `ga_prewarm_ttl_secs`, `ga_subagent_max_turns`.
- [x] 1.2 In `transport/lifecycle.py`, replace all `cfg.ga_crew_agent` / `GA_CREW_AGENT`
      references (the KiroCrew internal agent name written to config.local.json) with the
      literal `"kiro"` or a `_KC_AGENT_NAME = "kiro"` module constant. Same for
      `GA_PREWARM_TTL_SECS` → `_PREWARM_TTL_SECS = 300` and
      `GA_SUBAGENT_MAX_TURNS` → `_SUBAGENT_MAX_TURNS = 200`. Remove the
      `GA_PREWARM_ENABLED` gate — let `_prewarm_crew` always execute when called.
      Replace `TRANSPORT_DATA_DIR` / `cfg.transport_data_dir` with `"/data"` literal.
- [x] 1.3 In `transport/server.py`, replace `GA_CREW_AGENT`, `GA_ENABLE_SECURITY_HEADERS`,
      `GA_TLS_MIN_VERSION`, `GA_SUBAGENT_MAX_TURNS` module-level reads with the
      corresponding constants/literals. `_TLS_MIN_VERSION = "1.2"`. Remove the
      `GA_ENABLE_SECURITY_HEADERS` conditional — `SecurityHeadersMiddleware` always active.
- [x] 1.4 In `scripts/install.sh`, replace `GA_COMPOSE_RETRY_ATTEMPTS` and
      `GA_COMPOSE_RETRY_DELAY_SECS` reads with hardcoded constants
      `_COMPOSE_RETRY_ATTEMPTS=3` and `_COMPOSE_RETRY_DELAY_SECS=2`. Remove them
      from the defaults block and any compose env passthrough.
- [x] 1.5 Verify: `python3 -c "import transport.config; import transport.lifecycle; import transport.server"` passes cleanly.

## 2. Consolidate GA_CREW_AGENT (rename + replace GA_CREW_ACP_BACKEND + GA_AGENT_BACKENDS)

- [x] 2.1 In `transport/config.py`, add `ga_crew_agent: str = "kiro"` (new meaning:
      the ACP backend to use). In `from_env()`, read `GA_CREW_AGENT` first; if unset,
      fall back to `GA_CREW_ACP_BACKEND` with a deprecation warning log. Remove
      `ga_crew_acp_backend` and `ga_agent_backends` fields.
- [x] 2.2 In `transport/lifecycle.py` and `transport/server.py`, replace all
      `cfg.ga_crew_acp_backend` and `GA_CREW_ACP_BACKEND` with `cfg.ga_crew_agent`.
      Replace `cfg.ga_agent_backends` / `GA_AGENT_BACKENDS` with a frozenset derived
      from `cfg.ga_crew_agent.split(",")` where needed (e.g. login route validation).
- [x] 2.3 In `scripts/install.sh`, replace `GA_AGENT_BACKENDS` with `GA_CREW_AGENT` as
      the source for `AGENT_TOOLCHAINS`. First entry of `GA_CREW_AGENT` becomes the
      runtime backend passed to compose. Add deprecation warnings: if `GA_AGENT_BACKENDS`
      or `GA_CREW_ACP_BACKEND` are set, print a warning and map them to `GA_CREW_AGENT`
      for this run. Update compose template: replace `GA_CREW_ACP_BACKEND: ...` with
      `GA_CREW_AGENT: <first_entry>`.
- [x] 2.4 Update `tests/unit/test_agent_backends.py` and `test_agent_backends_parity.py`
      to use `GA_CREW_AGENT` instead of `GA_CREW_ACP_BACKEND`/`GA_AGENT_BACKENDS`.
      Add test: deprecated alias `GA_CREW_ACP_BACKEND` maps to `GA_CREW_AGENT` with
      a logged warning.

## 3. Fix GA_ORDERS_DIR — add volume mount

- [x] 3.1 In `scripts/install.sh`, before writing `compose.yml`, add a check: if
      `GA_ORDERS_DIR` is set but not an absolute path, print an error and abort; if set
      and path doesn't exist, print a warning but continue.
- [x] 3.2 In the compose template, add a conditional `- ${GA_ORDERS_DIR}:/mnt/orders:ro`
      volume entry for `ga-transport` when `GA_ORDERS_DIR` is non-empty, and set
      `GA_ORDERS_DIR: "/mnt/orders"` (fixed container path) in the environment block.

## 4. Fix GA_TLS_CERTFILE / GA_TLS_KEYFILE — add volume mount

- [x] 4.1 In `scripts/install.sh`, add a check: if either TLS var is set but not both,
      error with a clear message; if both are set and don't share the same parent
      directory, error.
- [x] 4.2 In the compose template, add a conditional `- <cert_dir>:/mnt/tls:ro` volume
      entry when both TLS vars are set; set `GA_TLS_CERTFILE: "/mnt/tls/<cert_basename>"`
      and `GA_TLS_KEYFILE: "/mnt/tls/<key_basename>"` as the container-side paths.

## 5. Fix lifecycle.py comment

- [x] 5.1 In `transport/lifecycle.py` around line 280, replace "Both TTLs floor at one
      hour." with an accurate comment: "The warm-marker TTL is floored at one hour via
      `_warm_marker_ttl_secs()`; `_TASK_TIMESTAMP_TTL_SECS` has no floor."

## 6. Prune ghostship.conf.example and update docs

- [x] 6.1 Remove from `config/ghostship.conf.example`: all vars now hardcoded (task 1),
      `GA_CREW_ACP_BACKEND`, `GA_AGENT_BACKENDS` (replaced by `GA_CREW_AGENT`),
      `PODMAN_SOCKET`, `KC_IMAGE`, `KC_BASE_IMAGE`, `GA_MACHINE_NAME`,
      `GA_SUBAGENT_TIMEOUT_SECS`, `GA_MIN_FREE_MEM_GB`, `GA_SPAWN_MIN_MEMORY_GB`,
      `GA_RESOURCE_PRESSURE_GB`, `GA_RESOURCE_CRITICAL_GB`,
      `GA_SPAWN_PRESSURE_ESCALATE_CYCLES`, `GA_DASHBOARD_PORT_RANGE_START`,
      `GA_DASHBOARD_PORT_RANGE_SIZE`, `GA_RATE_LIMIT_LOGIN_GET`,
      `GA_RATE_LIMIT_LOGIN_POST`, `GA_RATE_LIMIT_MCP`, `GA_RATE_LIMIT_FILES`,
      `GA_RATE_LIMIT_CREW_API`.
      Keep `GA_RATE_LIMIT_ENABLED` — it is the master kill-switch and is legitimately
      useful to operators; the per-endpoint vars are the noise.
- [x] 6.2 Add `GA_CREW_AGENT` to `ghostship.conf.example` in the agent backends section,
      replacing the `GA_AGENT_BACKENDS` + `GA_CREW_ACP_BACKEND` block. Document values:
      `kiro` (default), `claude`, `codex`, `opencode`. Note that `GA_CREW_ACP_BACKEND`
      is a deprecated alias.
- [x] 6.3 Update `docs/configuration.md`: remove hardcoded vars from the reference table;
      add an "Advanced / expert-only" section documenting the pruned vars that remain
      functional; update `GA_CREW_AGENT` entry; add PORT clarification (Caddy host port
      only; transport always 64057 inside container); update `GA_MAX_ACTIVE_CREWS` entry
      (values ≤ 0 all disable the limit).
- [x] 6.4 Update `GA_ORDERS_DIR` and TLS entries in docs and conf.example to reflect
      the new volume-mount behaviour.

## 7. Tests and verification

- [x] 7.1 Run `tests/run.sh --unit` — must pass after all changes.
- [x] 7.2 Verify install.sh deprecation path: set `GA_CREW_ACP_BACKEND=claude` in the
      environment and source the relevant install.sh parsing section in a subshell;
      assert the deprecation warning is printed and `GA_CREW_AGENT` is set to `claude`.
      Alternatively verify via the existing `tests/unit/test_agent_backends_parity.py`
      once it is updated in task 2.4.
- [x] 7.3 Verify hardcoding: grep for `GA_CREW_AGENT\b`, `TRANSPORT_DATA_DIR`,
      `GA_ENABLE_SECURITY_HEADERS`, `GA_TLS_MIN_VERSION`, `GA_PREWARM_ENABLED`,
      `GA_PREWARM_TTL_SECS`, `GA_SUBAGENT_MAX_TURNS` in transport/*.py — none should
      reference these as env-var reads in `from_env()` or as `cfg.*` attributes.
