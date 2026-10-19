# Design

## Context

See proposal.md for why. Current state that shapes the approach:

- `install.sh` generates `compose.yml`. `ga-transport` gets `HOST: ${HOST:-0.0.0.0}` and a hardcoded `PORT: "64057"`. It joins `ga-portside` and `ga-starboard` and publishes nothing. `ga-portal` publishes `"0.0.0.0:${PORT}:${PORT}"` and an unbound dashboard range, and joins `ga-portside` only.
- Caddy dials `ga-transport:64057` (`transport/caddy.py`, `install.sh` route JSON) and adds `X-Transport-Token` to every upstream request. `PortalSecretMiddleware` rejects requests without it, which is what stops crews on `ga-starboard` dialling the transport directly.
- The exposure check exists twice: `install.sh` (~L1089) and `transport/server.py` (`_load_api_key` warning, `_enforce_require_api_key`). Both read `HOST` and `GA_REQUIRE_API_KEY`.
- `yaml_config.py` flattens YAML to `KEY=value` lines. `_scalar_to_str` turns booleans into `"true"`/`"false"`, so `api_key: false` currently becomes `GA_API_KEY=false`.
- API key persistence: `--api-key` writes `DATA_DIR/ga-api-key`. Without the flag, the persisted file overwrites whatever `GA_API_KEY` the config produced. The CLI (`trn-cli` "Transport URL and bearer key resolved consistently") reads that same file to find the installed key.
- Readiness: `install.sh` succeeds if *either* a `podman exec` probe inside `ga-transport` or a host `curl` to `127.0.0.1:${PORT}` passes. The in-container probe passed even while every request through the portal returned 502, which is why the original break went unnoticed. `start.sh` probes `127.0.0.1:${PORT}` only.
- The CLI's `_inspect_installed_url` inspects `ga-transport`'s port bindings. `ga-transport` publishes none, so it always falls back to `http://localhost:64057`, and a non-default `PORT` is never discovered (an existing violation of `trn-cli`).

## Goals / Non-Goals

**Goals:**
- One meaning per setting: `HOST` is the portal's bind address, and `network.api_key` is the only authentication-posture setting.
- The exposure check is accurate: it evaluates exactly what is published.
- A broken loopback config like the one that prompted this change is no longer possible.

**Non-Goals:**
- Narrowing the transport to listen on `ga-portside` only (see Decisions).
- Changing the portal secret, TLS (`GA_PORTAL_TLS_MODE`), or `GA_PORTAL_DOMAIN` handling.
- `ghostship setup`/`init` default registration URL (they don't call the transport).

## Decisions

### 1. Transport listens on a fixed `0.0.0.0`, set in compose under a new name
The compose file sets `ga-transport`'s listen address explicitly (`GA_TRANSPORT_BIND: "0.0.0.0"`) and stops passing `HOST` to it. `Config` reads `GA_TRANSPORT_BIND` (default `0.0.0.0`) into a renamed field (`bind_host`). Nothing operator-facing exposes it.

*Why a new name rather than hardcoding `HOST: "0.0.0.0"` (the `PORT` precedent):* `HOST` inside the transport meaning something different from `HOST` in the yaml is exactly the confusion that caused this bug. A distinct name makes any leftover reader of `HOST` fail loudly in review and tests.

*Alternative, listen on the `ga-portside` address only:* rejected for now. The address is assigned dynamically, so it would need resolving at startup. Crews on `ga-starboard` are already kept out by `X-Transport-Token`, and the transport only *dials out* on starboard. This could be added later without changing any spec in this change.

### 2. The transport learns the portal's address via `GA_PORTAL_HOST`
`install.sh` passes the resolved `HOST` to `ga-transport` as `GA_PORTAL_HOST`. `server.py`'s exposure check and the URL fallback read it through `Config`. The transport never treats it as its own bind address.

### 3. One shared loopback test
A helper `is_loopback(host)` covers unset/empty, `localhost`, `::1` and anything in `127.0.0.0/8` (via `ipaddress`; non-IP strings other than `localhost` count as non-loopback). It lives in `transport/` for the transport, and `yaml_config.py` exposes the same logic as a subcommand (`yaml_config.py is-loopback <host>`) so `install.sh` doesn't reimplement it in bash. One implementation means the two checks can't drift.

### 4. API key opt-out encoding
`yaml_config.py` special-cases `network.api_key`:

| YAML value | Emitted env |
|:--|:--|
| non-empty string (not `"true"`/`"false"`) | `GA_API_KEY=<value>`, `GA_API_KEY_DISABLED=` |
| `false` | `GA_API_KEY=`, `GA_API_KEY_DISABLED=true` |
| absent / `null` / `""` | `GA_API_KEY=`, `GA_API_KEY_DISABLED=` |
| `true`, `"true"`, `"false"`, other types | error, non-zero exit |

`null` deliberately means unset, not opt-out. `api_key:` with nothing after it is an easy accident, and an accident must never disable authentication. `GA_REQUIRE_API_KEY` is removed from `DEFAULTS`/`_KEY_MAP`. A present `network.require_api_key` goes through a value-mapping step, not the path-rename table. `yaml_config.py` can't see the flag or the persisted key, so it only emits a deprecation warning and `GA_API_KEY_DEPRECATED_OFF=true` for `off`. `install.sh` applies it after Decision 5's resolution, as an opt-out only if no key was resolved from any source. That stops a leftover `require_api_key: off` from silently disabling a key set with `--api-key`. Conf migration writes `api_key: false` only when the conf has no `GA_API_KEY`.

`install.sh` passes `GA_API_KEY_DISABLED` to the transport instead of `GA_REQUIRE_API_KEY`.

### 5. Resolution order: flag > yaml > persisted file, with input and effective key in separate files
`install.sh` records whether the yaml set `network.api_key` (string or `false`) via a `GA_API_KEY_SOURCE=yaml` marker emitted by `yaml_config.py`. The persisted-flag restore runs only when neither the flag nor the yaml set it. `--api-key <key>` persists. `--api-key ""` deletes the persisted flag key and falls through to the yaml.

Two files in `DATA_DIR`:
- `ga-api-key.flag` is the *input*: only `--api-key` writes it.
- `ga-api-key` is the *effective* key. It's rewritten on every install, or deleted when there's no key or the opt-out is set.

The CLI keeps reading `ga-api-key` unchanged, so a yaml-only key is discoverable too. Without the split, either the CLI can't find a yaml key, or removing the key from the yaml silently falls back to a stale copy of it. One-time migration: if `ga-api-key` exists and `ga-api-key.flag` doesn't, copy it to `.flag` first, since every existing `ga-api-key` was written by `--api-key`.

*Alternative, the CLI reads the Podman secret:* rejected, because `podman secret inspect --showsecret` depends on the Podman version and needs a socket the CLI may not have.

### 6. `GA_HOST_URL` fallback computed in one place
`install.sh` computes the default only when `GA_HOST_URL` is unset: `http://localhost:${PORT}` for loopback or wildcard `HOST`, otherwise `http://${HOST}:${PORT}` (IPv6 bracketed). It passes the result as `GA_HOST_URL`, as it does today. The transport's own `localhost` fallbacks (`files.py`, `tools.py`) stay as a safety net for non-installer runs, but read `GA_PORTAL_HOST` the same way via a shared `Config` helper.

### 7. Readiness probes go through the portal
`install.sh` and `start.sh` both probe `GET {probe_base}/health` on the host. `probe_base` is `http://127.0.0.1:${PORT}` for loopback or wildcard `HOST` (`https` when `GA_PORTAL_TLS_MODE` is on, `-k` as today), otherwise `http://${HOST}:${PORT}`. The `podman exec` probe is kept only as a diagnostic: if it passes while the portal probe fails, the error says the transport is up but unreachable from `ga-portal`. Note that its hardcoded `${PORT}` is wrong whenever `PORT≠64057`; it should use `64057`. `/health` is already on Caddy's unauthenticated route list, so the probe needs no key.

### 8. CLI discovers the installed URL from `ga-transport`'s `GA_HOST_URL`
`_inspect_installed_url` reads `GA_HOST_URL` from `ga-transport`'s environment instead of its (empty) port bindings. `install.sh` always sets it to the public base URL: derived from `HOST`/`PORT` (Decision 6), or the operator's `--public-url`. That's exactly what a client should target, including the wildcard→`localhost` and IPv6-bracket handling. This brings the CLI back in line with the existing `trn-cli` spec, and makes it follow `HOST` without any CLI flag.

*Alternative, inspect `ga-portal`'s port bindings:* rejected. `ga-portal` also publishes the whole dashboard port range, so picking the main port means guessing, and a `--public-url` (for example a TLS hostname) would be ignored.

## Risks / Trade-offs

- [Upgraders who relied on the implicit `0.0.0.0` lose remote access] → `install.sh` prints a one-time notice when the resolved `HOST` is the new default and the previous `compose.yml` published on `0.0.0.0`, pointing at `network.host`. The release notes call out the BREAKING change.
- [Example-config users with `host: "0.0.0.0"` and no key now abort] → Intended. The abort message lists all three fixes.
- [`require_api_key: warn` users now abort] → Deprecation warning names `network.api_key: false` as the replacement.
- [`0.0.0.0` inside the container also listens on `ga-starboard`] → Already mitigated by `X-Transport-Token`. Narrowing is deferred (Decision 1).
- [Specific-IP `HOST` vs `ghostship setup`'s registered `localhost` URL] → Documented next to `HOST`, with `ghostship setup --url` as the fix. Other CLI subcommands follow `HOST` via Decision 8.
- [Podman machine on macOS may not honour a specific non-loopback host IP in a port binding (gvproxy forwarding); `127.0.0.1` and `0.0.0.0` are the well-trodden cases] → Task 6.4 verifies a specific-IP bind on macOS. If it's unsupported, `install.sh` rejects such `HOST` values on macOS with a clear error rather than publishing something different from what was asked.
- [Stricter readiness turns a silently broken install into a failed install] → Intended. The diagnostic distinguishes "transport down" from "portal can't reach transport".

## Migration Plan

1. Operators run `ghostship install` (or `upgrade`). `compose.yml` is regenerated and `ga-transport`/`ga-portal` are recreated. No crew impact.
2. The yaml is not rewritten. Deprecated `require_api_key` values are mapped at read time with a warning.
3. Rollback: reinstall the previous version. The old `install.sh` reads `network.host`/`network.api_key` as before. An `api_key: false` left in the yaml would be read by the old version as the literal key `"false"`, so remove it before rolling back. This goes in the release notes.
