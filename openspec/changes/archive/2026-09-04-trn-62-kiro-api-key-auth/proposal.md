## Why

The current auth flow requires a browser-based device code exchange (`POST /login` → open URL → confirm) before any crew can be launched. For headless/CI environments and Pro+ users with an API key, this interactive step is unnecessary friction. `KIRO_API_KEY` (or equivalent kiro-cli env var) can authenticate kiro-cli without a device flow, enabling fully headless ghostship deployments.

## What Changes

- Add `KIRO_API_KEY` config var to `transport/config.py` and `from_env()`. When set, this is injected as an env var into crew containers at creation time — kiro-cli inside the crew uses it directly.
- When `KIRO_API_KEY` is set, skip the device-auth flow entirely: `launch` does not call `_initiate_login()`, does not require `ga-kiro-auth` to exist, and does not call `inject_auth.py`. kiro-cli authenticates itself via the env var.
- When `KIRO_API_KEY` is unset, fall back to the existing device-code flow unchanged — Builder ID / free tier users are unaffected.
- Conditionally skip `inject_auth.py` (the `auth_b64` injection step in `_finish_crew_setup`) when `KIRO_API_KEY` is set — the env var replaces the SQLite row injection.
- Add `KIRO_API_KEY` to `install.sh` as an optional passed-through env var for the `ga-transport` container.
- Add `KIRO_API_KEY` to `config/ghostship.conf.example` with a comment explaining the two auth paths.
- Document both paths in `docs/auth.md`: a "Headless / API key" section and a note that Builder ID users continue to use device flow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-auth` — add `KIRO_API_KEY` path: when set, auth is satisfied by env var injection; device-code flow and `ga-kiro-auth` injection are skipped for that path.

## Impact

- `transport/config.py` — new `kiro_api_key` field
- `transport/lifecycle.py` — `_finish_crew_setup`: skip `_inject_auth` when `KIRO_API_KEY` set; pass API key as container env var
- `transport/server.py` — `launch`: skip `_initiate_login()` guard when `KIRO_API_KEY` set
- `scripts/install.sh` — pass `KIRO_API_KEY` through to `ga-transport` env
- `config/ghostship.conf.example` — document the new var
- `docs/auth.md` — new headless/API-key section
- Tests — add unit tests for the API key auth path
