# Auth & Security

> **Breaking change (TRN-233): backend credentials are no longer set in
> the config file (`ghostship.yaml` / the retired `ghostship.conf`) or delivered as Podman secrets.** The `ANTHROPIC_API_KEY`,
> `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY` and `KIRO_API_KEY` config entries
> are gone, and the installer ignores them with a warning if present. Backend
> credentials now live in `DATA_DIR/credentials/<backend>.json` and are managed
> with the `ghostship auth login|logout|status` CLI. **Upgrading drops every
> stored credential — log in again** with `ghostship auth login <backend>` for
> each enabled backend (the install wizard offers this automatically). Running
> crews fail to launch until you do; the first `launch` per backend returns a
> login URL. `backends.kiro.identity_center.url` / `.region` stay as config —
> they are the non-secret defaults for the Kiro Identity Center login.

## Managing credentials: `ghostship auth`

All backend auth is driven by one CLI, against the installed transport:

```bash
ghostship auth login <backend>    # store or replace a credential (kiro|claude|codex)
ghostship auth logout <backend>   # cancel any pending login and clear the stored credential
ghostship auth status             # show what is configured for every backend
```

- `login` presents a numbered **method menu** per backend (or pass `--method`).
- Secrets are read from a hidden terminal prompt, or from stdin when piped —
  they never appear in `argv` or in command output.
- The transport URL and bearer key are **discovered automatically** from the
  installed containers (Podman inspect), so no flags are needed on a local
  keyed install. Override with `--url` / `--api-key`, or the `GHOSTSHIP_URL` /
  `GHOSTSHIP_API_KEY` env vars. Pasted secrets are refused over plain HTTP to a
  remote host unless `--insecure` is passed.
- `ghostship auth status --json` emits machine-readable per-backend state
  (`{backend: {configured, method, stored_at}}`), with no secret values.
- `ghostship auth logout <backend>` is how you both log out and abort a login.
  It always ends with no stored credential and no pending login, whatever the
  starting state. It is idempotent: it returns success with
  `aborted_pending_login` when it cancelled a flow. It does not touch running
  crews, so relaunch or nuke them to drop their credential.

Per-backend methods:

| Backend | Methods (`--method`) |
|:--------|:---------------------|
| kiro    | `builder-id`, `identity-center`, `api-key` |
| claude  | `oauth` (Pro/Max authorisation code), `api-key`, `setup-token` |
| codex   | `chatgpt` (ChatGPT sign-in), `api-key` |

## Kiro auth

`ga-kiro-auth` is the kiro-cli `auth_kv` payload (base64-encoded JSON), stored at
`DATA_DIR/ga-kiro-auth` (mode `0600`). `DATA_DIR` is bind-mounted read/write into
`ga-transport` as `/data`.

### Log in

```bash
# Builder ID (default, all tiers) — a browser device-code flow:
ghostship auth login kiro --method builder-id

# IAM Identity Center (org licensing). Flags default to the installed
# KIRO_IDENTITY_PROVIDER / KIRO_REGION config, and --license pro is added:
ghostship auth login kiro --method identity-center \
  --identity-provider https://d-xxxxxxxxxx.awsapps.com/start/#/ \
  --region <region>

# Pro+ API key (headless, no browser step):
ghostship auth login kiro --method api-key
```

- The Identity Center start URL **must include `/#/`**.
- Omit `--method` to pick from the menu. For device and authorisation-code
  flows the CLI prints the activation URL and code, then polls until you
  approve (or the flow times out).
- Complete auth before calling `launch`. Any crew created before auth completes
  is unauthenticated and cannot be salvaged — nuke it.

### Identity provider config

The Identity Center login defaults come from `--config` file → CLI flags →
interactive prompt. These settings stay in `config/ghostship.yaml` (non-secret),
under `backends.kiro`:

```yaml
# config/ghostship.yaml
backends:
  kiro:
    identity_center:
      url: "https://identitycenter.amazonaws.com/ssoins-abc123"
      region: "us-east-1"
```

```bash
./install.sh --config ./idp.conf
# then: ghostship auth login kiro --method identity-center
```

### Uninstall retention

`uninstall.sh` keeps `ga-kiro-auth` **and `DATA_DIR/credentials/`** so a later
install can reuse the logins. Pass `--purge-auth` to remove both.

### Secret rotation

When tokens expire: `ghostship auth logout kiro` to clear stale auth, then
`ghostship auth login kiro` for fresh tokens. When the new login completes, its
auth is injected into running kiro crews. Logout itself leaves running crews
unchanged; relaunch or nuke a crew to drop the credential it launched with.

### Auth API

Three HTTP endpoints on the MCP port. Not MCP tools — agents cannot call them. Require `Authorization: Bearer <key>` when `GA_API_KEY` is set. The CLI drives these for you. All login paths are `POST /login/{backend}/{method}`; status is `GET /login/{backend}`; logout is `POST /logout/{backend}`.

```
UNAUTHENTICATED  ──[POST /login/kiro/builder-id]──►  PENDING  ──[GET /login/kiro → complete]──►  AUTHENTICATED
                                                                                                       │
                ◄──────────────────────────────[POST /logout/kiro]────────────────────────────────────┘
```

**`POST /login/kiro/builder-id`** / **`POST /login/kiro/identity-center`** — start the device / Identity Center flow and return `login_url` and `code`. Identity Center takes `{start_url?, region?}`, defaulting to the configured `KIRO_IDENTITY_PROVIDER` / `KIRO_REGION`, adds `--license pro`, and returns 400 if a value is still missing. **`POST /login/kiro/api-key`** stores a pasted Pro+ key. Completion replaces any existing credential (no 409).

**`GET /login/kiro`** — polls completion and returns status plus any pending flow and the configured Identity Center defaults. On success writes `ga-kiro-auth`, injects auth into running kiro crews (not claude or codex crews), returns `complete`.

**`POST /logout/kiro`** — cancels any pending flow (removing its login container), then removes the stored credential and the legacy `ga-kiro-auth` file. Returns `200 {"status": "logged_out"}`, adding `"aborted_pending_login": true` when a flow was cancelled. Idempotent: with nothing stored or pending it still returns 200. Returns 500 if the credential cannot be deleted, or if podman is unavailable so a pending login cannot be cancelled (the credential is still removed). Running crews are not touched: they keep the credential they launched with until relaunched or nuked.

---

## Claude auth

Claude-backend crews authenticate with a credential stored by the transport and
resolved per launch. Pick a method with `ghostship auth login claude`:

| Method | For |
|:-------|:----|
| `setup-token` | Unattended/server deployments. A long-lived token from `claude setup-token`, run once on your own machine. Every crew uses the same token, so the OAuth staleness under [Re-authenticate](#re-authenticate) does not apply. **Recommended.** |
| `api-key` | Anthropic pay-per-token API key. |
| `oauth` | Claude Pro/Max subscription, interactive authorisation-code flow (below). |

### Prerequisites

Enable the Claude backend by adding `claude` to `backends.agent` in your
`config/ghostship.yaml` and re-running `ghostship install`, which builds the `claude`
CLI into the crew image. Login works whenever `claude` is enabled, even while
another backend is the default.

### Setup-token (headless, recommended)

1. On your own machine, run `claude setup-token`, approve in the browser, and
   copy the token it prints.
2. Store it in the transport:

   ```bash
   ghostship auth login claude --method setup-token
   # paste the token at the hidden prompt (or pipe it on stdin)
   ```

New Claude-backend crews launch without a login prompt. The token is never
written to the config file and never appears in command output.

### Rotate

The token is long-lived but does expire. When crews start failing Claude auth,
run `claude setup-token` again and re-run `ghostship auth login claude --method
setup-token`. The credential is resolved per launch, so new and relaunched crews
pick up the new value with no restart.

## Claude OAuth login (interactive)

`ga-claude-auth` is a tar archive of `~/.claude/` (the credential directory written
by the `claude` CLI), stored at `DATA_DIR/ga-claude-auth` (mode `0600`).

This method (`ghostship auth login claude --method oauth`) is for operators with a
Claude Pro/Max subscription who prefer not to maintain a separate API-tier account.
For unattended or server deployments, prefer the setup-token method above. The CLI
drives the HTTP flow below for you; the raw endpoints are documented for reference.

### Prerequisites

1. Enable the Claude backend: add `claude` to `backends.agent` in your
   `config/ghostship.yaml` and re-run `ghostship install`, which builds the `claude` CLI
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

This cancels any pending Claude login, then deletes the stored credential (and
`ga-claude-auth`, if present). It is idempotent. Running Claude-backend crews are
not touched: they keep the credential they launched with, so relaunch or nuke a
crew to drop it.

### Credential precedence

Each Claude-backend crew gets exactly one credential from the store, chosen by the
method recorded for the `claude` backend:

1. `api-key` (Anthropic API key).
2. `setup-token` (`CLAUDE_CODE_OAUTH_TOKEN`).
3. `oauth` (`ga-claude-auth`, copied into the crew's `~/.claude/`).

There is one active credential per backend — logging in with a new method replaces
the previous one. `backends.claude.base_url` (`ANTHROPIC_BASE_URL`, non-secret) may still be set in
`config/ghostship.yaml` to point at a proxy.

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

**`POST /logout/claude`** — cancels any pending flow (removing its login container), then removes the stored credential and `ga-claude-auth`. Returns `200 {"status": "logged_out"}`, with `"aborted_pending_login": true` when a flow was cancelled. Idempotent: with nothing stored or pending it still returns 200. Returns 500 if the credential cannot be deleted, or if podman is unavailable so a pending login cannot be cancelled (the credential is still removed). Running crews are not touched.

---

## Codex ChatGPT login (TRN-172, TRN-233)

`ga-codex-auth` is a tar archive of `~/.codex/` (the credential directory holding
`auth.json`, written by the Codex login flow), stored at `DATA_DIR/ga-codex-auth`
(mode `0600`).

Run `ghostship auth login codex` and pick a method: `api-key` (OpenAI
pay-per-token key) or `chatgpt` (ChatGPT sign-in, for operators with a ChatGPT
subscription who prefer not to maintain a separate API-tier account). The CLI
drives the HTTP flow below for you.

### Prerequisites

1. Enable the Codex backend: add `codex` to `backends.agent` in your
   `config/ghostship.yaml` and re-run `ghostship install`, which builds the `codex-acp`
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

This cancels any pending Codex login, then deletes the stored credential (and
`ga-codex-auth`, if present). It is idempotent. Running Codex-backend crews are
not touched: they keep the credential they launched with, so relaunch or nuke a
crew to drop it.

### Credential precedence

There is one active credential per backend. Logging in with `--method api-key`
replaces a stored `chatgpt` credential and vice versa — the method recorded for
the `codex` backend is the one used. `backends.codex.base_url` (`OPENAI_BASE_URL`, non-secret) may still be
set in `config/ghostship.yaml` to point at a proxy.

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

**`POST /logout/codex`** — cancels any pending flow (removing its login container), then removes the stored credential and `ga-codex-auth`. Returns `200 {"status": "logged_out"}`, with `"aborted_pending_login": true` when a flow was cancelled. Idempotent: with nothing stored or pending it still returns 200. Returns 500 if the credential cannot be deleted, or if podman is unavailable so a pending login cannot be cancelled (the credential is still removed). Running crews are not touched.

---

An optional static bearer credential protecting the MCP endpoint. Set it in
`config/ghostship.yaml` or on the command line (the flag wins and is saved for
later installs):

```yaml
network:
  api_key: "<your-secret-key>"
```

```bash
./install.sh --api-key <your-secret-key>
```

The key is delivered as a Podman secret — never as an environment variable. `./install.sh --api-key ""` clears the saved flag key.

A key is optional while `network.host` is loopback (the default, `127.0.0.1`).
For any other host the install aborts without one, unless you opt out
explicitly with `network.api_key: false` — for deployments that put their own
auth layer in front (Tailscale, VPN, reverse proxy).

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
- **CI secret scan.** `scripts/security_scan.py` runs in the `security-scan` CI job and fails the build on a likely committed live secret.

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
- `scripts/security_scan.py` flags string-built SQL and fails the build.

---

## Using the CLI

```bash
# Store or replace a credential for a backend. Presents a method menu (or pass
# --method); for device/authorisation-code flows it prints the URL + code and
# polls until you approve or the flow times out (~5 min).
ghostship auth login <backend>      # kiro | claude | codex

# Cancel any pending login and clear the stored credential for a backend.
ghostship auth logout <backend>

# Show per-backend credential status (add --json for machine-readable output).
ghostship auth status
```

URL and key are discovered from the installed containers, so no flags are needed
on a local keyed install. Override for non-default or remote transports:

```bash
ghostship auth login claude --url https://remote.example.com --api-key <key>
```

Resolution order is `--url` flag > `GHOSTSHIP_URL` env var > the installed port
(via Podman inspect) > `http://localhost:64057`; the bearer key follows the same
order with `GHOSTSHIP_API_KEY`. The transport must be running; the command fails
immediately (naming the URL it tried) if it is unreachable. Pasted secrets are
refused over plain HTTP to a remote host unless `--insecure` is passed.
