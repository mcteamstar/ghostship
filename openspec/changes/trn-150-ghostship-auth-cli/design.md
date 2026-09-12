## Context

The `ghostship` CLI is a single-file Python 3 stdlib-only script (`ghostship` at the repo root). Subcommands are registered in `_COMMANDS: dict[str, Callable]`. The transport REST API handles device auth at `POST /login` (starts flow, returns `{login_url, user_code}`) and `GET /login` (polls status, returns `{status}` where status is `pending`, `complete`, or `expired`). Logout is `POST /logout`. All three are public (no Bearer required) since auth is what you're establishing.

## Goals / Non-Goals

**Goals:**
- `ghostship auth login` walks the operator through the device flow interactively
- `ghostship auth logout` revokes the current session
- Works with local and remote transports via `--url` / `GHOSTSHIP_URL`
- Zero new dependencies — stdlib only

**Non-Goals:**
- Storing or managing tokens locally (the transport owns session state)
- SSO / OAuth flows other than device code
- Checking current auth status without attempting a flow

## Decisions

**D1 — `auth` as a subcommand group, not a flat subcommand**

`ghostship auth login` / `ghostship auth logout` rather than `ghostship login` / `ghostship logout`. Keeps auth operations grouped, leaves room for `ghostship auth status` later, and matches the TRN-150 ticket spec. The `cmd_auth` dispatcher handles `auth <subcommand>` and prints its own usage if no sub-subcommand is given.

**D2 — `urllib.request` for HTTP, no httpx**

The CLI script has a strict zero-dependency constraint. `urllib.request` handles `POST /login` (JSON body), `GET /login` (polling), and `POST /logout` cleanly with a small helper. No reason to reach for httpx in the CLI layer.

**D3 — Polling loop with progress dots**

`auth login` prints the URL + code once, then prints a dot every 5 seconds while polling `GET /login`. On `complete`: success message. On `expired` or after 300s: timeout message that re-prints the URL. On connection error: error message. Interval and timeout are hardcoded (5s / 300s) — no flags needed.

**D4 — URL resolution order**

`--url` flag > `GHOSTSHIP_URL` env var > `http://localhost:64057`. Strips trailing slash. The same helper is reused by both `login` and `logout`.

**D5 — `auth` dispatches via its own sub-dict**

```python
_AUTH_COMMANDS = {"login": auth_login, "logout": auth_logout}

def cmd_auth(args):
    if not args or args[0] in ("--help", "-h"):
        print(_AUTH_USAGE)
        return 0
    sub = args[0]
    handler = _AUTH_COMMANDS.get(sub)
    if handler is None:
        print(f"error: unknown auth subcommand '{sub}'")
        return 1
    return handler(args[1:])
```

Registered as `_COMMANDS["auth"] = cmd_auth`.

## Risks / Trade-offs

- **Transport must be running** — `auth login` will fail immediately if the transport is not up. This is acceptable; the error message includes the URL so the operator knows where it tried.
- **No token caching** — the CLI cannot tell the operator "you are currently authenticated". A future `ghostship auth status` could call `GET /version` or a dedicated endpoint to check. Out of scope here.
