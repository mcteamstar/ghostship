## 1. URL resolution helper

- [ ] 1.1 Add `_resolve_transport_url(args)` helper that reads `--url` from args list, falls back to `GHOSTSHIP_URL` env var, then `http://localhost:64057`; strips trailing slash
- [ ] 1.2 Add `_parse_api_key(args)` helper that reads `--api-key` from args list (returns `None` if absent)
- [ ] 1.3 Add `_http_json(url, method, body=None, api_key=None)` helper using `urllib.request` — sends JSON body if provided, returns parsed JSON response, raises `urllib.error.URLError` on connection failure

## 2. auth login

- [ ] 2.1 Add `auth_login(args)` function: parse `--url` / `--api-key` from args, call `POST /login` via helper, print activation URL and user code clearly
- [ ] 2.2 Implement polling loop: every 5s call `GET /login`, print a dot each iteration, stop on `complete` (print success) or `expired` / 300s elapsed (print timeout with URL, exit non-zero)
- [ ] 2.3 Handle connection error on `POST /login` — print message including URL tried, exit non-zero
- [ ] 2.4 Handle already-authenticated response from transport (if applicable) — print "Already authenticated." and exit 0

## 3. auth logout

- [ ] 3.1 Add `auth_logout(args)` function: parse `--url` / `--api-key`, call `POST /logout`, print "Logged out." and exit 0
- [ ] 3.2 Handle connection error — print message including URL tried, exit non-zero

## 4. cmd_auth dispatcher

- [ ] 4.1 Add `_AUTH_USAGE` string documenting `ghostship auth login` and `ghostship auth logout` with flags
- [ ] 4.2 Add `_AUTH_COMMANDS = {"login": auth_login, "logout": auth_logout}` dict
- [ ] 4.3 Add `cmd_auth(args)` dispatcher: no args → print `_AUTH_USAGE`, unknown sub-subcommand → error, else delegate
- [ ] 4.4 Register `"auth": cmd_auth` in `_COMMANDS`
- [ ] 4.5 Add `  auth login/logout    Authenticate or deauthenticate with the transport` to `_USAGE` string

## 5. docs

- [ ] 5.1 Add a short "CLI auth" section to `docs/auth.md` showing `ghostship auth login` and `ghostship auth logout` usage

## 6. verification

- [ ] 6.1 `python3 -m py_compile ghostship` — syntax clean
- [ ] 6.2 Manual smoke: `ghostship auth login` against academy, complete the flow, confirm "Authenticated successfully."
- [ ] 6.3 Manual smoke: `ghostship auth logout` against academy, confirm "Logged out."
- [ ] 6.4 Manual smoke: `ghostship auth login --url http://invalid:9999`, confirm error message includes the URL and exits non-zero
