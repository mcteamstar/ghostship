## 1. transport/config.py — remove dead and removed fields

- [x] 1.1 Remove the `ga_file_ttl_secs` field from the `Config` dataclass and its `from_env()` assignment (`os.environ.get("GA_FILE_TTL_SECS", "300")`).
- [x] 1.2 Remove `ga_pickup_max_poll_secs` field and its `from_env()` assignment.
- [x] 1.3 Remove `ga_memory_wait_secs` field and its `from_env()` assignment.
- [x] 1.4 Remove `kc_gateway_token_ttl` field, its validator function `_validate_token_ttl`, and its `from_env()` assignment.
- [x] 1.5 Remove `ga_enforce_https_redirect` field and its `from_env()` assignment.
- [x] 1.6 Remove `ga_csp_enforce` field and its `from_env()` assignment.
- [x] 1.7 Remove `ga_portal_admin_url` field and its `from_env()` assignment.
- [x] 1.8 Remove `ga_portal_port` field and its `from_env()` assignment (`GA_PORTAL_PORT`). The `port` field (reading `PORT`) already exists and is the canonical replacement.

## 2. transport/server.py — remove module-level constants and hardcode values

- [x] 2.1 Remove `GA_FILE_TTL_SECS = cfg.ga_file_ttl_secs` and replace all usages with the literal `300`.
- [x] 2.2 Remove `GA_PICKUP_MAX_POLL_SECS = cfg.ga_pickup_max_poll_secs` and replace all usages with the literal `30`.
- [x] 2.3 Remove `GA_MEMORY_WAIT_SECS = cfg.ga_memory_wait_secs` and replace all usages with the literal `60`.
- [x] 2.4 Remove `KC_GATEWAY_TOKEN_TTL = cfg.kc_gateway_token_ttl` and replace all usages with the literal `"24h"`. Check `transport/lifecycle.py` — it also has `KC_GATEWAY_TOKEN_TTL` imported/used; hardcode there too.
- [x] 2.5 Remove `GA_ENFORCE_HTTPS_REDIRECT = cfg.ga_enforce_https_redirect` and replace the conditional that gates the HTTPS redirect behaviour with `False` (redirect disabled — Caddy now owns redirects).
- [x] 2.6 Remove `GA_CSP_ENFORCE = cfg.ga_csp_enforce` and replace the conditional that gates CSP header emission with unconditional enforcement (always emit CSP headers).
- [x] 2.7 Remove the `cfg.ga_portal_admin_url` usage — find the function that returns it (around line 718) and hardcode `"http://ga-portal:2019"` directly.

## 3. scripts/install.sh — rename and remove from defaults block

- [x] 3.1 Find the `GA_PORTAL_PORT=64057` line in the built-in defaults block (around line 93) and remove it. The `PORT=64057` line (around line 52) stays.
- [x] 3.2 Replace all remaining `${GA_PORTAL_PORT:-64057}` references in the compose template, Caddy config generation, and health check with `${PORT:-64057}` (or just `${PORT}`).
- [x] 3.3 Remove `HOST` from the built-in defaults block. (The Python field stays; this just removes the install.sh default.)
- [x] 3.4 Remove `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE` from the built-in defaults block if present.
- [x] 3.5 Add a migration guard: before sourcing `--config <file>`, check if the file contains `GA_PORTAL_PORT`. If found, print a deprecation warning and sed-substitute `GA_PORTAL_PORT` → `PORT` in a temp copy before sourcing.
- [x] 3.6 Remove the removed vars from the compose `environment:` block in install.sh (around lines 656–677): `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_MEMORY_WAIT_SECS`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`. These are passed into the transport container — removing them means the transport uses its hardcoded values, which is correct.
- [x] 3.7 Add explicit `podman rm -f ga-portal` before compose up to prevent port conflict on upgrade (rootlessport binding not atomically released by `--force-recreate` alone).

## 4. config/ghostship.conf.example — restructure and update

- [x] 4.1 Add a `# ── Common ──` section header at the top containing only: `PORT`, `GA_HOST_URL`, `GA_API_KEY`, `KIRO_API_KEY`, `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`, `KC_MODEL_OVERRIDE`, `KC_MODEL_DEFAULT`, `GA_GIT_AUTHOR_NAME`, `GA_GIT_AUTHOR_EMAIL`.
- [x] 4.2 Move remaining vars into a `# ── Advanced ──` section below, keeping their existing section groupings.
- [x] 4.3 Remove the `GA_PORTAL_PORT` commented-out line; add a note under `PORT` that `GA_PORTAL_PORT` is the deprecated alias.
- [x] 4.4 Remove `HOST` from the file (or move to Advanced with a note that it's not normally needed).
- [x] 4.5 Remove `GA_PORTAL_ADMIN_URL`, `GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`, `KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE` from the file entirely.

## 5. docs/configuration.md — update variable list and add model precedence

- [x] 5.1 Remove the 8 removed variables from the reference table/list.
- [x] 5.2 Update `GA_PORTAL_PORT` entry to a deprecated alias note pointing to `PORT`.
- [x] 5.3 Add a **Model precedence** section documenting the chain: `dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model field > `KC_MODEL_DEFAULT` > KiroCrew built-in default.

## 6. Fix tests that reference removed constants

- [x] 6.1 `tests/unit/test_server.py` line 592 — `patch.object(server, "GA_PICKUP_MAX_POLL_SECS", 5)`: this patches a module-level constant that will no longer exist. Replace with a direct patch of the literal or a mock of the timeout in the function being tested.
- [x] 6.2 `tests/unit/test_server.py` lines 1218–1238 — tests that set `server.KC_GATEWAY_TOKEN_TTL` and `lifecycle.KC_GATEWAY_TOKEN_TTL` directly: with the constant hardcoded, these tests need to either patch the value at the call site (e.g. mock `_request_token`) or be removed if they only tested configurability of a now-hardcoded value.
- [x] 6.3 `tests/unit/test_server.py` line 1284 — assertion `assertIn('KC_GATEWAY_TOKEN_TTL', installer)`: update to not expect this var in install output.
- [x] 6.4 `tests/unit/test_trn70_security.py` line 233 — docstring references `GA_ENFORCE_HTTPS_REDIRECT=0`: update docstring to reflect that redirect is now unconditionally disabled (Caddy-owned).
- [x] 6.5 `tests/unit/test_trn93_security_hardening.py` lines 453–460 — tests that assert a warning is logged about `KC_GATEWAY_TOKEN_TTL`: these test a config validation path that no longer exists. Remove or update to test that no such warning is emitted (since the field is hardcoded).
- [x] 6.6 `tests/unit/test_trn102_portal_dashboard_session.py` lines 89, 95 — `patch.object(server, "KC_GATEWAY_TOKEN_TTL", "24h")`: replace with a direct mock of the token request or remove if the test now works with the hardcoded value.

## 7. CHANGELOG.md

- [x] 7.1 Add a breaking change entry for `GA_PORTAL_PORT` → `PORT` rename with auto-migration note.
- [x] 7.2 Add entries for the 8 removed vars (internal, hardcoded at existing defaults — no operator action needed beyond the `GA_PORTAL_PORT` rename).
