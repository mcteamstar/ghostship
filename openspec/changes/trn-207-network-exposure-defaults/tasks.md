# Tasks

## 1. Bind-address warning — install.sh

- [x] 1.1 Add `GA_REQUIRE_API_KEY` variable parsing in `scripts/install.sh` after the existing variable defaults block; accept `warn`, `error`, `off`; default `warn`
- [x] 1.2 After port and API-key variables are resolved, add a check: if `GA_API_KEY` is empty and the published port address is not `127.0.0.1`/`::1`, emit a WARNING to stderr naming the bind address and suggesting `GA_API_KEY` or `HOST=127.0.0.1`; if `GA_REQUIRE_API_KEY=error`, exit non-zero; skip if `GA_REQUIRE_API_KEY=off`
- [x] 1.3 Add `GA_REQUIRE_API_KEY: "${GA_REQUIRE_API_KEY:-warn}"` to the compose `environment:` block so the transport container sees it

## 2. Bind-address warning — transport startup

- [x] 2.1 In `transport/server.py` (or the startup init path), log a `WARNING` when `GA_API_KEY` is absent and `GA_HOST` / `HOST` is not `127.0.0.1`/`::1`, so the risk is visible in transport logs not just at install time

## 3. Docs and config

- [x] 3.1 Add `GA_REQUIRE_API_KEY` entry to `docs/configuration.md`: three values (`warn`/`error`/`off`), default, and when each applies
- [x] 3.2 Add commented-out `GA_REQUIRE_API_KEY=warn` entry to `config/ghostship.conf.example` with a one-line description
