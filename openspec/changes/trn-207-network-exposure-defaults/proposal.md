## Why

Default ghostship install binds on `0.0.0.0` with no API key. This is intentional —
ghostship is a local-first tool and open-by-default reduces friction for the majority of
users running it on a desktop or homelab. Operators choosing to expose it remotely are
responsible for their own lockdown.

However, there is no signal at install time that the transport is unauthenticated and
network-reachable. A single startup warning surfaces the risk without blocking anything.

## What Changes

- `install.sh`: when `GA_API_KEY` is empty and the published port address is not
  `127.0.0.1` or `::1`, emit a WARNING to stderr naming the bind address and suggesting
  `GA_API_KEY` or `HOST=127.0.0.1`.
- `GA_REQUIRE_API_KEY`: optional escape hatch. `warn` (default) — print the warning.
  `error` — abort install. `off` — silence it. Passed through to the transport container.
- Transport startup: log the same warning at WARNING level when `GA_API_KEY` is absent
  and `HOST` is not loopback, so it appears in transport logs too (not just at install time).
- `docs/configuration.md` and `ghostship.conf.example`: add `GA_REQUIRE_API_KEY` entry.

## Capabilities

### Modified Capabilities

- `installation`

## Impact

`scripts/install.sh`, `transport/server.py` (or startup init), `docs/configuration.md`,
`config/ghostship.conf.example`. Small — 2–3 install.sh lines, 1 log line in transport,
1 new config entry in docs.
