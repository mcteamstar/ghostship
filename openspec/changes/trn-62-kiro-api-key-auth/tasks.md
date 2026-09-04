## 1. Config and module-level export

- [x] 1.1 Add `kiro_api_key: str = ""` to `Config` in `transport/config.py`
- [x] 1.2 Add `kiro_api_key=os.environ.get("KIRO_API_KEY", "")` to `Config.from_env()`
- [x] 1.3 Export `KIRO_API_KEY = cfg.kiro_api_key` in `transport/server.py` (alongside `KIRO_LICENSE`)

## 2. Skip device-code flow when API key is set

- [x] 2.1 In `transport/server.py` `launch()`: wrap the `_initiate_login()` call in `if not KIRO_API_KEY:` so the device-code guard is bypassed when an API key is configured
- [x] 2.2 Verify: `launch` with `KIRO_API_KEY` set and no `ga-kiro-auth` file completes crew setup without returning `auth_required`

## 3. Inject API key as env var into crew containers

- [x] 3.1 In `transport/lifecycle.py` `_finish_crew_setup`: add `KIRO_API_KEY` to the env vars passed to `podman create`, conditionally (only when `KIRO_API_KEY` is non-empty)
- [x] 3.2 In `_finish_crew_setup`: skip the `_inject_auth(podman, container, auth_b64)` call when `KIRO_API_KEY` is set

## 4. Install script and config

- [x] 4.1 In `scripts/install.sh`: add `KIRO_API_KEY: "${KIRO_API_KEY:-}"` to the `ga-transport` service env block in the `compose.yml` generation (alongside `KIRO_LICENSE`)
- [x] 4.2 Add a `KIRO_API_KEY` commented entry to `config/ghostship.conf.example` with a comment explaining both auth paths

## 5. Docs

- [x] 5.1 Add a "Headless / API key auth (Pro+)" section to `docs/auth.md`, explaining: set `KIRO_API_KEY` in `ghostship.conf`, re-run `install.sh`, no `POST /login` needed
- [x] 5.2 Add a note that Builder ID / device-code flow is unchanged when `KIRO_API_KEY` is unset

## 6. Tests

- [x] 6.1 Add unit test: `launch` with `KIRO_API_KEY` set — `_initiate_login` is NOT called and `_inject_auth` is NOT called
- [x] 6.2 Add unit test: `launch` with `KIRO_API_KEY` unset — existing device-code path unchanged (existing tests remain passing)
- [x] 6.3 Add unit test: crew container env vars include `KIRO_API_KEY` when set, absent when unset
- [x] 6.4 Run `tests/run.sh --unit` — all tests pass
