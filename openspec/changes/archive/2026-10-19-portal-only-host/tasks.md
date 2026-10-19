# Tasks

## 1. yaml_config.py — HOST default, api_key states, require_api_key deprecation

- [x] 1.1 Change the `HOST` default in `DEFAULTS` to `127.0.0.1`. Verify: `python3 scripts/lib/yaml_config.py resolve --repo /dev/null --xdg /dev/null` emits `HOST=127.0.0.1`.
- [x] 1.2 Special-case `network.api_key` per design Decision 4: string → `GA_API_KEY`; `false` → `GA_API_KEY_DISABLED=true` with empty `GA_API_KEY`; absent/`null`/`""` → both empty; `true`, `"true"`, `"false"` and non-scalar values → error, non-zero exit. Emit `GA_API_KEY_SOURCE=yaml` when the yaml set a string or `false`. Verify: new cases in `tests/unit/test_yaml_config.py` cover each row of the table and pass.
- [x] 1.3 Remove `GA_REQUIRE_API_KEY` from `DEFAULTS` and `_KEY_MAP`. For `network.require_api_key`, print a deprecation warning naming `network.api_key`, and emit `GA_API_KEY_DEPRECATED_OFF=true` only for `off` (`error`/`warn` emit nothing). Verify: `test_yaml_config.py` covers `off`, `error` and `warn`, and none emits `GA_REQUIRE_API_KEY`.
- [x] 1.4 Apply the same mapping in conf→yaml auto-migration (`GA_REQUIRE_API_KEY=off` with no `GA_API_KEY` → `network.api_key: false`; otherwise drop it). Verify: a migration test using a conf with `GA_REQUIRE_API_KEY=off` produces yaml with `api_key: false` and no `require_api_key`.
- [x] 1.5 Add an `is-loopback <host>` subcommand that prints `true`/`false` (unset/empty, `localhost`, `::1`, `127.0.0.0/8` → true). Verify: unit tests cover `""`, `127.0.0.1`, `127.1.2.3`, `::1`, `localhost`, `0.0.0.0`, `::`, `192.168.1.10`.

## 2. install.sh — portal bind, transport env, API-key resolution and check

- [x] 2.1 Publish `ga-portal` on `${HOST}` for both `PORT` and the dashboard range (bracket IPv6 literals), and stop passing `HOST` to `ga-transport`. Pass `GA_TRANSPORT_BIND: "0.0.0.0"`, `GA_PORTAL_HOST: "${HOST}"` and `GA_API_KEY_DISABLED`, and drop `GA_REQUIRE_API_KEY` from its environment. Verify: `test_install.py` compose-generation assertions for the default (`127.0.0.1`), `0.0.0.0` and `192.168.1.10` cases, with `ga-transport` env containing no `HOST`.
- [x] 2.2 Rework API-key resolution per design Decision 5:
  - Order is flag > yaml (`GA_API_KEY_SOURCE=yaml`) > `DATA_DIR/ga-api-key.flag`.
  - `--api-key ""` deletes `.flag` and falls through.
  - One-time copy of a legacy `ga-api-key` to `.flag`.
  - After resolving, apply `GA_API_KEY_DEPRECATED_OFF` as the opt-out only if no key was resolved.
  - Rewrite the effective `ga-api-key` (mode 600) or delete it when there's no key or the opt-out is set.

  Verify: `test_install.py` covers all five "API key resolution order" scenarios, both deprecated-`off` scenarios, and the legacy-file migration.
- [x] 2.3 Replace the `GA_REQUIRE_API_KEY` check with the portal-address check, using `yaml_config.py is-loopback`. For a non-loopback `HOST` with an unset key: print the WARNING (address, port, three fixes) and exit non-zero before any container starts. With the opt-out: print the explicit-choice WARNING and continue. Update the auth-status echo to report "disabled (explicit opt-out)" for the opt-out. Verify: `test_install.py` covers abort (`0.0.0.0` and `192.168.1.10`), loopback pass, opt-out pass with warning, and key-set pass with no warning.
- [x] 2.4 Compute the `GA_HOST_URL` default from `HOST` when unset: `localhost` for loopback or wildcard, otherwise `http://${HOST}:${PORT}`. Verify: `test_install.py` asserts the generated `GA_HOST_URL` for the default, `0.0.0.0` and `192.168.1.10`.
- [x] 2.5 Print a one-time notice when the resolved `HOST` is the default `127.0.0.1` and the existing `compose.yml` published `ga-portal` on `0.0.0.0`, pointing the operator at `network.host`. Verify: `test_install.py` case with a pre-existing `0.0.0.0` compose file shows the notice, and a fresh install doesn't.
- [x] 2.6 Replace readiness in `install.sh` (~L1462) and `scripts/start.sh` (~L199) with the portal probe from design Decision 7. Keep the `podman exec` probe as a diagnostic only, fixed to target `64057`. Verify: `test_install.py` asserts the probe URL for the loopback, wildcard and specific-IP cases, and on a host where Caddy returns 502 the install exits non-zero with the portal-to-transport message.
- [x] 2.7 Update the `install.sh` header and config comments (L6, ~L257–263, ~L1088) to describe `HOST` as the portal bind address and `network.api_key: false` as the opt-out. Verify: `grep -n GA_REQUIRE_API_KEY scripts/install.sh` returns only the deprecation-handling lines.

## 3. Transport — fixed listen address, portal-address check, URL fallback

- [x] 3.1 In `transport/config.py`, replace `host` (from `HOST`) with `bind_host` (from `GA_TRANSPORT_BIND`, default `0.0.0.0`), and add `portal_host` (from `GA_PORTAL_HOST`, default `127.0.0.1`) and `api_key_disabled` (from `GA_API_KEY_DISABLED`). Add the shared `is_loopback()` helper and a `public_base_url()` helper implementing the Decision 6 fallback. Verify: `tests/unit/test_config.py` host tests rewritten for the new fields and the Config↔`ghostship.yaml.example` sync invariant updated; `pytest tests/unit/test_config.py` passes.
- [x] 3.2 In `transport/server.py`, make uvicorn use `cfg.bind_host`. Rewrite `_load_api_key`'s warning and `_enforce_require_api_key` (rename to `_enforce_api_key_requirement`) to evaluate `cfg.portal_host` and `cfg.api_key_disabled`. Delete the stale `-p "127.0.0.1:PORT:PORT"` comment at ~L379. Verify: unit tests where a `0.0.0.0` bind plus `127.0.0.1` portal and no key starts; a non-loopback portal, no key and no opt-out exits non-zero; and a non-loopback portal with the opt-out starts and logs a WARNING.
- [x] 3.3 Remove the `HOST` alias in `transport/tools.py`, and route the CORS-origin fallback (~L719–733) and `files.py`'s presigned-URL fallback through `public_base_url()`. Verify: unit tests assert `KIROCREW_CORS_ORIGINS` and presigned URLs use `http://localhost:{PORT}` for a loopback portal and `http://192.168.1.10:{PORT}` for that portal host when `GA_HOST_URL` is unset, and `GA_HOST_URL` when set.
- [x] 3.4 `grep -rnw HOST transport/` returns no reads of the `HOST` env var. Verify by running the grep.

## 4. CLI — installed URL discovery

- [x] 4.1 Make `_inspect_installed_url` in `ghostship` read `GA_HOST_URL` from `ga-transport`'s environment (design Decision 8). Verify: unit tests with mocked `podman inspect` output for a loopback, a specific-IP and a `PORT=9000` install, plus an install with no `GA_HOST_URL`; and with `PORT=9000` installed, CLI URL resolution targets port 9000 with no `--url`.

## 5. Config example and docs

- [x] 5.1 Update `config/ghostship.yaml.example`: set `network.host: "127.0.0.1"` with a comment saying it's the address `ga-portal` publishes on; document `network.api_key`'s three states; remove `require_api_key`. Verify: the yaml parses, and the Config↔example sync test passes.
- [x] 5.2 Update `docs/configuration.md`:
  - Rewrite the `HOST` row (portal bind, default `127.0.0.1`, transport listens on fixed `0.0.0.0` internally, CLI `--url` note for specific IPs).
  - Replace the `GA_REQUIRE_API_KEY` row with `network.api_key` states plus a deprecation note.
  - Update the `GA_HOST_URL` default description and the `network` section key list (~L254).

  Verify: `grep -n 'require_api_key\|GA_REQUIRE_API_KEY' docs/configuration.md` hits only the deprecation note.
- [x] 5.3 Add a CHANGELOG entry marking the `HOST` default and `require_api_key` removal as BREAKING, including the rollback caveat for `api_key: false`. Verify: the entry is present under the unreleased version.

## 6. Integration check

- [x] 6.1 Run the full unit suite. Verify: `pytest tests/unit/` exits 0 with no new failures.
- [x] 6.2 On a real host with `network.host: 127.0.0.1` and no key, run `ghostship install`. Verify:
  - `curl -s -o /dev/null -w '%{http_code}' http://localhost:64057/mcp` is not `502`.
  - `podman port ga-portal` shows `127.0.0.1` only.
  - The `ga-portal` logs show no `connection refused`.
- [x] 6.3 Set `network.host: 0.0.0.0` with no key and run `ghostship install`. Verify that it aborts with the WARNING. Then set `network.api_key: false`, rerun, and verify that it installs with the explicit-choice WARNING. _(2026-10-19, macOS: abort verified — exit 1 in 0.9s before any build, containers untouched. Opt-out verified with the LAN IP (see 6.4): install printed the explicit-choice WARNING and the transport logged it at startup.)_
- [x] 6.4 On macOS (Podman machine), install with `network.host` set to the Mac's LAN IP and an API key. Verify that `podman port ga-portal` shows that IP, and that `curl http://<lan-ip>:64057/health` succeeds from another machine on the LAN. If the binding is unsupported, implement the macOS rejection from design Risks and verify that it errors clearly. _(2026-10-19: with `host: 10.1.10.85` and `api_key: false`, ga-portal published all 65 ports on 10.1.10.85 only; gvproxy listened on 10.1.10.85:64057; `/health` and an unauthenticated `/mcp` POST returned 200 at the LAN IP and 127.0.0.1 got no connection; CLI discovery returned `http://10.1.10.85:64057`. So Podman machine honours a specific host IP, and the macOS rejection isn't needed. The second-machine request was waived by Tony on this local evidence. Restored to loopback afterwards.)_
