## Why

The device auth flow (`POST /login` → poll `GET /login` → redirect URL + code) is only accessible via the REST API or implicitly through a `launch()` call. Operators who need to re-authenticate — expired token, new identity, fresh install without an agent — have no discoverable CLI path. The `ghostship` CLI already owns transport lifecycle; auth should live there too.

## What Changes

Add a `ghostship auth` subcommand group with two sub-subcommands:

- `ghostship auth login` — initiates the device auth flow: calls `POST /login`, prints the activation URL and code, polls until the user completes auth or the flow times out, reports success or failure.
- `ghostship auth logout` — calls `POST /logout` to revoke the current session.

Both commands accept `--url <transport-url>` and `--api-key <key>` for non-default or remote transports. Transport URL defaults to `GHOSTSHIP_URL` env var, then `http://localhost:64057`.

## Capabilities

### Modified Capabilities

- `trn-cli`: adds the `auth` subcommand group with `login` and `logout` sub-subcommands.

## Impact

- `ghostship` CLI script — new `cmd_auth` function, `_COMMANDS["auth"]` entry, usage string updated
- No new dependencies — stdlib `urllib.request` only, matching the CLI's zero-dep constraint
- `docs/auth.md` — add a short "Using the CLI" section referencing `ghostship auth login`
