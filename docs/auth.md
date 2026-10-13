# Auth & Security

## Kiro auth

`ga-kiro-auth` is the kiro-cli `auth_kv` payload (base64-encoded JSON), stored at
`DATA_DIR/ga-kiro-auth` (mode `0600`). `DATA_DIR` is bind-mounted read/write into
`ga-transport` as `/data`.

### Headless / API key auth (Pro+)

For CI or Pro+ users with a kiro-cli API key, skip the device-code flow entirely.

```bash
cp config/ghostship.conf.example config/ghostship.conf
# Set KIRO_API_KEY="<your-api-key>" in ghostship.conf, then:
./install.sh --config config/ghostship.conf
```

When `KIRO_API_KEY` is set, `launch` skips `_initiate_login()`, the key is injected
as `KIRO_API_KEY` into each crew container, and the `inject_auth.py` SQLite step is
skipped.

### First login

Complete auth before calling `launch`. Any crew created before auth completes is
unauthenticated and cannot be salvaged — nuke it.

**1. Install with identity provider settings**

```bash
cp config/ghostship.conf.example config/ghostship.conf
./install.sh --config config/ghostship.conf

# Or inline:
./install.sh \
  --identity-provider https://d-xxxxxxxxxx.awsapps.com/start/#/ \
  --region <region> \
  --license pro
```

- The start URL **must include `/#/`**.
- `--license pro` is required for IAM Identity Center.

**2. Trigger the login flow**

```bash
curl -sX POST http://localhost:64057/login | jq
```

```json
{
  "status": "pending",
  "login_url": "https://d-xxxxxxxxxx.awsapps.com/start/#/device?user_code=XXXX-XXXX",
  "code": "XXXX-XXXX"
}
```

**3. Open the URL and approve the device** using your org credentials.

**4. Confirm completion**

```bash
curl -s http://localhost:64057/login | jq .status
# → "complete"
```

**5. Launch** — the transport is ready.

### Identity provider config

Resolved in order: `--config` file → CLI flags → interactive prompt.

```bash
# idp.conf
KIRO_IDENTITY_PROVIDER="https://identitycenter.amazonaws.com/ssoins-abc123"
KIRO_REGION="us-east-1"
KIRO_LICENSE="pro"
```

```bash
./install.sh --config ./idp.conf
```

### Uninstall retention

`uninstall.sh` keeps `ga-kiro-auth` so a later install can reuse the login. Pass `--purge-auth` to remove it too.

### Secret rotation

When tokens expire: `POST /logout` to clear stale auth, then `POST /login` for fresh tokens. Running crews receive fresh auth immediately — no nuke or relaunch needed.

### Auth API

Three HTTP endpoints on the MCP port. Not MCP tools — agents cannot call them. Require `Authorization: Bearer <key>` when `GA_API_KEY` is set.

```
UNAUTHENTICATED  ──[POST /login]──►  PENDING  ──[GET /login → complete]──►  AUTHENTICATED
                                                                                    │
                ◄──────────────────────────────────[POST /logout]──────────────────┘
```

**`POST /login`** — starts device auth, returns `login_url` and `code`. Returns 409 if already authenticated.

**`GET /login`** — polls completion. On success writes `ga-kiro-auth`, injects auth into all running crews, returns `complete`.

**`POST /logout`** — deletes `ga-kiro-auth` and clears auth from every running crew.

---

## Claude headless auth (recommended)

For unattended and server deployments, give the transport a long-lived Claude token
instead of logging in through the browser. The token comes from `claude setup-token`,
which you run once on your own machine. It is delivered like `KIRO_API_KEY`: set in
`ghostship.conf`, stored as the Podman secret `ga-claude-code-oauth-token`, and injected
into each Claude-backend crew as `CLAUDE_CODE_OAUTH_TOKEN`. Every crew uses the same
token, so the OAuth refresh problem described under
[Re-authenticate](#re-authenticate) does not apply.

### Prerequisites

Enable the Claude backend by adding `claude` to `GA_CREW_AGENT` in your
`ghostship.conf`.

### Authenticate

1. On your own machine, run `claude setup-token`, approve in the browser, and copy
   the token it prints.
2. Add it to `ghostship.conf`:

   ```bash
   CLAUDE_CODE_OAUTH_TOKEN="<token>"
   ```

3. Re-run `ghostship install`. New Claude-backend crews launch without a login
   prompt.

`install.sh` ignores a `CLAUDE_CODE_OAUTH_TOKEN` exported in your shell. Only the
value in `ghostship.conf` is used.

### Rotate

The token is long-lived but does expire. When crews start failing Claude auth, run
`claude setup-token` again, replace the value in `ghostship.conf`, and re-run
`ghostship install`. The token is fixed in a crew's environment when the crew is
created, so evac and relaunch existing Claude-backend crews to pick up the new one.

## Claude OAuth login (interactive)

`ga-claude-auth` is a tar archive of `~/.claude/` (the credential directory written
by the `claude` CLI), stored at `DATA_DIR/ga-claude-auth` (mode `0600`).

This path is an alternative to `ANTHROPIC_API_KEY` for operators with a
Claude Pro/Max subscription who prefer not to maintain a separate API-tier account.
For unattended or server deployments, prefer the headless auth path above.

### Prerequisites

1. Enable the Claude backend: add `claude` to `GA_CREW_AGENT` in your
   `ghostship.conf` and re-run `ghostship install`, which builds the `claude` CLI
   into the crew image.
2. To make Claude the default for new crews, also set `GA_CREW_AGENT=claude` (deprecated alias: `GA_CREW_ACP_BACKEND=claude`).
   Login works whenever `claude` is enabled, even while another backend is the
   default.

### Authenticate

**1. Start the login flow**

```bash
curl -sX POST http://localhost:64057/login/claude | jq
```

```json
{
  "status": "pending",
  "login_url": "https://claude.com/cai/oauth/authorize?...",
  "code": null
}
```

**2. Approve in your browser.** Open `login_url` and sign in with your Claude
account (Pro or Max). After approval, the browser shows a code of the form
`<code>#<state>`. Copy it.

**3. Submit the code** (the second step, required for Claude):

```bash
curl -sX POST http://localhost:64057/login/claude/code \
  -H 'Content-Type: application/json' \
  -d '{"code": "<code>#<state>"}'
# → 202 {"status": "submitted"}
```

The transport writes the code to the CLI and the token exchange runs. Submit it
once; a second submission returns 409. The code is never logged.

**4. Confirm completion**

```bash
curl -s http://localhost:64057/login/claude | jq .status
# → "pending" until the credential is saved, then "complete"
```

Completion means `~/.claude/.credentials.json` exists and is non-empty inside the
login container. Other files, such as the `backups/` directory, do not count.

If no code is submitted within 15 minutes of starting the login, the poll also returns `410`. If the exchange does not finish within 120 seconds of submitting the code, the
poll returns `410` with `{"status": "expired"}`, the login container is removed,
and the audit log records a failed login. Start again from step 1.

**5. Launch** — the transport is ready. Each new crew will receive `~/.claude/`
injected at setup time.

### Re-authenticate

Claude OAuth tokens obtained via this flow may expire. Each crew gets its own copy
of `ga-claude-auth`, and the first crew to refresh the token can leave the stored
copy stale for crews launched later. The headless token path above does not have
this limitation.

To refresh an OAuth token:

```bash
# Clear the old credential
curl -sX POST http://localhost:64057/logout/claude

# Start a fresh login flow
curl -sX POST http://localhost:64057/login/claude | jq
```

### Logout

```bash
curl -sX POST http://localhost:64057/logout/claude
```

This deletes `ga-claude-auth` and runs `rm -rf ~/.claude/` inside every running
Claude-backend crew. Existing crew sessions become unauthenticated; relaunch them
after logging in again.

### Credential precedence

Each Claude-backend crew gets exactly one credential, chosen in this order:

1. `ANTHROPIC_API_KEY`.
2. `CLAUDE_CODE_OAUTH_TOKEN`.
3. `ga-claude-auth`, copied into the crew's `~/.claude/`.

The two settings are passed to the crew under the same names. Before TRN-226 the
API key setting was `GA_CREW_ANTHROPIC_API_KEY`; that name still works with a
deprecation warning.

A lower entry is only used when every entry above it is unset.

### Claude OAuth API

Four HTTP endpoints on the MCP port. Require `Authorization: Bearer <key>` when
`GA_API_KEY` is set. Available only while `claude` is in `GA_CREW_AGENT`; otherwise `POST /login/claude` and `POST /login/claude/code` return 400 naming `GA_CREW_AGENT`. Logout always works.

```
UNAUTHENTICATED  ──[POST /login/claude]──►  PENDING  ──[POST /login/claude/code]──►  CODE SUBMITTED  ──[GET /login/claude → complete]──►  AUTHENTICATED
                                                                                               │
               ◄──────────────────────────────────────[POST /logout/claude]────────────────────┘
```

**`POST /login/claude`** — starts the Claude OAuth authorisation flow inside an
ephemeral `ga-claude-login-*` container. Returns `{"login_url": "...", "code": null}`.
Returns 409 if already authenticated or flow in progress.

**`POST /login/claude/code`** — body `{"code": "<code>#<state>"}`, the value the browser
shows after approval. Writes it to the CLI and returns 202. Returns 404 if no flow
is awaiting a code, 409 if a code was already submitted, and 400 for a malformed body.
The code is never logged.

**`GET /login/claude`** — polls completion. On success writes `ga-claude-auth` and
returns `{"status": "complete"}`. Returns `{"status": "pending"}` while waiting.
Returns 404 if no flow is in progress, and 410 `{"status": "expired"}` when a
submitted code did not complete within 120 seconds.

**`POST /logout/claude`** — deletes `ga-claude-auth` and wipes `~/.claude/` from
every running Claude-backend crew. Returns 409 if not authenticated via OAuth.

---

## Codex OAuth login (TRN-172)

`ga-codex-auth` is a tar archive of `~/.codex/` (the credential directory holding
`auth.json`, written by the Codex login flow), stored at `DATA_DIR/ga-codex-auth`
(mode `0600`).

This path is an alternative to `OPENAI_API_KEY` for operators with a
ChatGPT subscription who prefer not to maintain a separate API-tier account.

### Prerequisites

1. Enable the Codex backend: add `codex` to `GA_CREW_AGENT` in your
   `ghostship.conf` and re-run `ghostship install`, which builds the `codex-acp`
   adapter into the crew image (ONE package — it ships its own Codex binary).
2. To make Codex the default for new crews, also set `GA_CREW_AGENT=codex` (deprecated alias: `GA_CREW_ACP_BACKEND=codex`).
   Login works whenever `codex` is enabled, even while another backend is the
   default.

### Authenticate

**1. Trigger the Codex login flow**

```bash
curl -sX POST http://localhost:64057/login/codex | jq
```

```json
{
  "status": "pending",
  "login_url": "https://auth.openai.com/...",
  "code": null
}
```

The `code` field may be `null` — the Codex login flow can surface a browser-based
sign-in with no separate device code.

**2. Open the URL in your browser** and approve the request using your OpenAI /
ChatGPT account.

**3. Confirm completion**

```bash
curl -s http://localhost:64057/login/codex | jq .status
# → "complete"
```

**4. Launch** — the transport is ready. Each new crew will receive `~/.codex/`
injected at setup time.

### Re-authenticate

Codex OAuth tokens may expire. To refresh:

```bash
# Clear the old credential
curl -sX POST http://localhost:64057/logout/codex

# Start a fresh login flow
curl -sX POST http://localhost:64057/login/codex | jq
```

### Logout

```bash
curl -sX POST http://localhost:64057/logout/codex
```

This deletes `ga-codex-auth` and runs `rm -rf ~/.codex/` inside every running
Codex-backend crew. Existing crew sessions become unauthenticated; relaunch them
after logging in again.

### Credential precedence

When both `OPENAI_API_KEY` and `ga-codex-auth` are present, the API key
takes precedence. OAuth credentials are only used when the API key is unset.

### Codex OAuth API

Three HTTP endpoints on the MCP port. Require `Authorization: Bearer <key>` when
`GA_API_KEY` is set. Available only while `codex` is in `GA_CREW_AGENT`; otherwise `POST /login/codex` returns 400 naming `GA_CREW_AGENT`. Logout always works.

```
UNAUTHENTICATED  ──[POST /login/codex]──►  PENDING  ──[GET /login/codex → complete]──►  AUTHENTICATED
                                                                                              │
              ◄──────────────────────────────────────[POST /logout/codex]────────────────────┘
```

**`POST /login/codex`** — starts the Codex OAuth login flow inside an ephemeral
`ga-codex-login-*` container. Returns `{"status": "pending", "login_url": "..."}`.
Returns 409 if already authenticated or a flow is in progress, and 400 if
`codex` is not in `GA_CREW_AGENT`.

**`GET /login/codex`** — polls completion. On success writes `ga-codex-auth` and
returns `{"status": "complete"}`. Returns `{"status": "pending"}` while waiting.
Returns 404 if no flow is in progress.

**`POST /logout/codex`** — deletes `ga-codex-auth` and wipes `~/.codex/` from
every running Codex-backend crew. Idempotent: returns 200 even when already
unauthenticated (nothing to clear).

---

An optional static bearer credential protecting the MCP endpoint.

```bash
./install.sh --api-key <your-secret-key>
```

The key is delivered as a Podman secret — never as an environment variable. To disable: `./install.sh --api-key ""`.

To rotate: `./install.sh --api-key <new-key>` — rewrites the file, recreates the secret, restarts the transport (~2s). Update all MCP clients with the new bearer token.

**Notes:**
- Plain HTTP is appropriate only for loopback or a trusted private tunnel. Use TLS for remote deployments.
- `GA_API_KEY` protects the MCP endpoint only. File-transfer routes use HMAC presigned URLs separately.

---

## Admiral mail signing

At crew launch the transport generates an **Ed25519 keypair**. The private seed lives host-side only — used by `captain.py` to sign standing orders — and never enters the crew container. The public key is delivered as a read-only, root-owned Podman secret at `/run/secrets/.admiral_public_key`.

Every standing order written to `/var/mail/captain` carries an `X-Admiral-Sig:` header. Raven calls `verify-admiral-sig` to confirm authenticity before acting.

**Residual risk — replay:** a correctly signed order can be re-delivered verbatim and will still verify. Signature validity proves authenticity of origin, not freshness.

**Policy signing:** a separate `policy_signing_key` signs `security_policy.json` via HMAC-SHA256. A tampered policy causes a mismatch and the gateway refuses to start. `policy_signing_key` is distinct from the Admiral seed — an agent reading `admission_policy.json` cannot forge Admiral standing orders.

**SEL signing key (KiroCrew 0.9.0+):** the Security Event Log (SEL) signing key is a **KiroCrew gateway-internal credential** and, as of KiroCrew 0.9.0, lives under `$KIROCREW_HOME/trust/` (the consolidated trust root the 0.9.0 governance work introduced). ghostship does not read, sign with, or verify against the SEL key today. If a future feature needs to read or verify SEL audit entries, it MUST resolve the key under `$KIROCREW_HOME/trust/` — never a hardcoded pre-0.9.0 location. Do not confuse the SEL key with ghostship's own `.local_secret` (the gateway's internal-API secret, used by `transport/lifecycle.py` for dashboard-cookie writes) or `policy_signing_key` (ghostship's own policy HMAC key). A static guardrail test (`tests/unit/test_trn_221_no_hardcoded_sel_path.py`) fails CI if a pre-0.9.0 SEL path literal is reintroduced under `transport/`. See TRN-221 (`trn-221-kc090-sel-key-trust-dir`).

**Storage:** `crews.json` stores only a non-reversible `sha256:<hex[:16]>` identifier for each secret. The Admiral Ed25519 private seed is persisted to `DATA_DIR/secrets/<crew_id>` (mode `0600`) so the transport can sign standing orders after launch.

### Threat model

| Scope | Posture |
|:------|:--------|
| Single operator (local) | `DATA_DIR` accessible only to the transport user. |
| Multi-operator | `crews.json` fingerprints are non-reversible. Restrict `DATA_DIR` to mode `0700`. |
| Agent-level | Agent can forge security policy signatures but not Admiral standing orders. |

---

## Dashboard session auth

Dashboard ports are protected by a session cookie gate via Portal (Caddy). See [portal.md](portal.md) for setup.

```
Browser ──GET :64058/──▶ ga-portal
                            │
                            ├─ forward_auth ──GET /dashboard/auth──▶ ga-transport
                            │                 valid gs_session?
                            │                 ├─ YES → 200 + X-Crew-Cookie
                            │                 └─ NO  → 401 → redirect to /dashboard/login
                            │
                            └─ (on 200) reverse_proxy ──▶ gs-{crew_id}:5476
```

`gs_session` cookies have a configurable TTL (`GA_PORTAL_SESSION_TTL_SECS`, default 24 h). Sessions are in-memory and reset on transport restart.

| Resource | Protection |
|:---------|:-----------|
| MCP / files | Caddy Bearer check + transport middleware (defence-in-depth) |
| Dashboard ports | `forward_auth` → `gs_session` cookie gate |
| TLS | Caddy-terminated (`GA_PORTAL_TLS_MODE`) |

---

## Secrets management

- **Redaction.** `SecretRedactionFilter` is installed on the root logger at startup. Any value passed to `security.register_secret` is scrubbed from every log record and error.
- **Admiral private key never enters the container.** No key material passes through a `podman exec` argument list or appears in `/proc/<pid>/cmdline`.
- **`crews.json` stores identifiers only.** Non-reversible `sha256:<hex[:16]>` fingerprints only — never plaintext secrets.
- **CI secret scan.** `tests/security_scan.py` runs in the `security-scan` CI job and fails the build on a likely committed live secret.

### Rotating `GA_API_KEY`

```bash
./install.sh --api-key <new-key>
```

### Rotating the file-URL signing secret

`GA_FILE_SECRET` can be overridden via env var; rotating it invalidates outstanding presigned URLs (which are short-lived by design).

---

## Transport security

`SecurityHeadersMiddleware` emits `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP, and HSTS (`max-age` two years) on every response. HTTPS is detected from the scheme or `X-Forwarded-Proto`.

HTTPS redirect is handled unconditionally by Caddy. Minimum TLS is 1.2.

## Input validation

- `security.validate_str` checks type, length, and format server-side, independent of client checks.
- All `auth_kv` access uses parameterized SQL — no string-built queries.
- `tests/security_scan.py` flags string-built SQL and fails the build.

---

## Using the CLI

```bash
# Start the device auth flow: prints an activation URL + code, then polls
# until you complete authentication (or the flow times out after ~5 min).
ghostship auth login

# Revoke the current transport session.
ghostship auth logout
```

Both commands accept `--url` / `--api-key` for non-default or remote transports:

```bash
ghostship auth login --url https://remote.example.com --api-key <key>
```

The transport URL is resolved as `--url` > `GHOSTSHIP_URL` env var >
`http://localhost:64057`. The transport must be running; `auth login` fails
immediately (with the URL it tried) if it is unreachable.
