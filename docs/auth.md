# Auth & Security

## Managing credentials: `ghostship auth`

All backend auth is driven by one CLI:

```bash
ghostship auth login <backend>    # store or replace a credential (kiro|claude|codex)
ghostship auth logout <backend>   # cancel any pending login and clear the stored credential
ghostship auth status             # show what is configured for every backend
```

Credentials live in `DATA_DIR/credentials/` and are resolved per crew launch — not in the config file.

- `login` presents a numbered method menu per backend (or pass `--method`).
- Secrets are read from a hidden terminal prompt or stdin — never appear in `argv` or output.
- The transport URL and bearer key are **discovered automatically** from the installed containers (Podman inspect). Override with `--url` / `--api-key`, or `GHOSTSHIP_URL` / `GHOSTSHIP_API_KEY` env vars.
- `ghostship auth logout <backend>` cancels any pending login and clears the stored credential. It does not touch running crews — relaunch or nuke to drop a crew's credential.

Per-backend methods:

| Backend | Methods (`--method`) |
|:--------|:---------------------|
| kiro    | `builder-id`, `identity-center`, `api-key` |
| claude  | `oauth` (Pro/Max), `api-key`, `setup-token` |
| codex   | `chatgpt` (ChatGPT sign-in), `api-key` |

## Kiro auth

### Log in

```bash
# Builder ID (default, all tiers) — browser device-code flow:
ghostship auth login kiro --method builder-id

# IAM Identity Center (org licensing):
ghostship auth login kiro --method identity-center \
  --identity-provider https://d-xxxxxxxxxx.awsapps.com/start/#/ \
  --region <region>

# API key (headless):
ghostship auth login kiro --method api-key
```

The Identity Center start URL **must include `/#/`**. Omit `--method` to pick from the menu. Complete auth before calling `launch` — crews created before auth completes cannot be salvaged (nuke them).

### Identity provider config

Identity Center defaults live in `config/ghostship.yaml`:

```yaml
backends:
  kiro:
    identity_center:
      url: "https://identitycenter.amazonaws.com/ssoins-abc123"
      region: "us-east-1"
```

### Secret rotation

When tokens expire: `ghostship auth logout kiro` then `ghostship auth login kiro`. New auth is injected into running kiro crews. Running crews keep their launch-time credential until relaunched or nuked.

### Uninstall retention

`uninstall.sh` keeps `DATA_DIR/credentials/` so a later install can reuse logins. Pass `--purge-auth` to remove them.

### Auth API

HTTP endpoints on the MCP port — driven by the CLI, not MCP tools. Require `Authorization: Bearer <key>` when `GA_API_KEY` is set.

```
UNAUTHENTICATED  ──[POST /login/kiro/builder-id]──►  PENDING  ──[GET /login/kiro → complete]──►  AUTHENTICATED
                ◄──────────────────────────────────────[POST /logout/kiro]────────────────────────────────────────┘
```

- **`POST /login/kiro/builder-id`** / **`POST /login/kiro/identity-center`** — starts the flow, returns `login_url` and `code`.
- **`POST /login/kiro/api-key`** — stores a pasted API key.
- **`GET /login/kiro`** — polls completion. On success writes auth and returns `complete`.
- **`POST /logout/kiro`** — cancels any pending flow, removes the credential. Idempotent. Running crews unaffected.

---

## Claude auth

### Methods

| Method | For |
|:-------|:----|
| `setup-token` | Unattended/server deployments. Long-lived token from `claude setup-token`. **Recommended.** |
| `api-key` | Anthropic pay-per-token API key. |
| `oauth` | Claude Pro/Max subscription, interactive authorisation-code flow. |

### Prerequisites

Enable the Claude backend by adding `claude` to `backends.agent` in `config/ghostship.yaml` and re-running `ghostship install`.

### Setup-token (headless, recommended)

1. On your own machine: `claude setup-token`, approve in browser, copy the token.
2. `ghostship auth login claude --method setup-token` and paste the token.

The token is long-lived but does expire. When crews fail Claude auth, run `claude setup-token` again and re-run the login. New and relaunched crews pick up the new value.

### OAuth (interactive)

```bash
ghostship auth login claude --method oauth
```

The CLI starts a flow, prints the URL, and polls for completion. After approval the browser shows `<code>#<state>` — the CLI submits it automatically. If no code is submitted within 15 minutes, or the exchange doesn't complete within 120 seconds, the flow expires.

OAuth tokens may expire over time. Re-authenticate with `ghostship auth logout claude` then `ghostship auth login claude`.

### Credential precedence

One active credential per backend. Logging in with a new method replaces the previous one. `backends.claude.base_url` (non-secret) can be set in `config/ghostship.yaml` to point at a proxy.

### Auth API

```
UNAUTHENTICATED  ──[POST /login/claude]──►  PENDING  ──[POST /login/claude/code]──►  CODE SUBMITTED  ──[GET /login/claude → complete]──►  AUTHENTICATED
               ◄──────────────────────────────────────────────[POST /logout/claude]──────────────────────────────────────────────────────────────────────┘
```

- **`POST /login/claude`** — starts the OAuth flow. Returns `{"login_url": "..."}`. Returns 409 if already authenticated or flow in progress.
- **`POST /login/claude/code`** — body `{"code": "<code>#<state>"}`. Returns 202. The code is never logged.
- **`GET /login/claude`** — polls completion. Returns `complete` / `pending` / `410 expired`.
- **`POST /logout/claude`** — cancels pending flow, removes credential. Idempotent. Running crews unaffected.

---

## Codex auth

### Prerequisites

Enable the Codex backend by adding `codex` to `backends.agent` in `config/ghostship.yaml` and re-running `ghostship install`.

### Authenticate

```bash
ghostship auth login codex   # presents method menu: chatgpt or api-key
```

For `chatgpt`: the CLI starts a flow, prints the URL, and polls for completion. Approve in your browser.

### Credential precedence

One active credential per backend. `backends.codex.base_url` (`OPENAI_BASE_URL`, non-secret) can be set in `config/ghostship.yaml` to point at a proxy.

### Auth API

```
UNAUTHENTICATED  ──[POST /login/codex]──►  PENDING  ──[GET /login/codex → complete]──►  AUTHENTICATED
              ◄──────────────────────────────────────[POST /logout/codex]───────────────────────────────┘
```

- **`POST /login/codex`** — starts the OAuth flow. Returns `{"status": "pending", "login_url": "..."}`.
- **`GET /login/codex`** — polls completion. Returns `complete` / `pending`.
- **`POST /logout/codex`** — cancels pending flow, removes credential. Idempotent. Running crews unaffected.

---

## Transport API key

An optional static bearer credential protecting the MCP endpoint. Set in `config/ghostship.yaml`:

```yaml
network:
  api_key: "<your-secret-key>"
```

Or on the command line: `./install.sh --api-key <key>`.

A key is optional while `network.host` is loopback (the default). For any other host the install requires one, unless you set `network.api_key: false` for deployments with their own auth layer.

To rotate: `./install.sh --api-key <new-key>`. Update all MCP clients with the new token.

---

## Admiral mail signing

At crew launch the transport generates an **Ed25519 keypair**. The private seed stays host-side and never enters the container. The public key is delivered as a read-only, root-owned Podman secret at `/run/secrets/.admiral_public_key`.

Every standing order written to `/var/mail/captain` carries an `X-Admiral-Sig:` header. Raven calls `verify-admiral-sig` to confirm authenticity before acting.

A separate `policy_signing_key` signs `security_policy.json` via HMAC-SHA256. A tampered policy causes a mismatch and the gateway refuses to start.

**Storage:** `crews.json` stores only a non-reversible `sha256:<hex[:16]>` fingerprint per secret. The Admiral Ed25519 private seed is persisted to `DATA_DIR/secrets/<crew_id>` (mode `0600`).

### Threat model

| Scope | Posture |
|:------|:--------|
| Single operator (local) | `DATA_DIR` accessible only to the transport user. |
| Multi-operator | Fingerprints are non-reversible. Restrict `DATA_DIR` to mode `0700`. |
| Agent-level | An agent can read `policy_signing_key` and could forge a policy signature, but cannot forge Admiral standing orders. |

---

## Secrets management

- **Redaction.** `SecretRedactionFilter` scrubs registered secret values from every log record and error.
- **Admiral private key never enters the container.** No key material passes through `podman exec` argv.
- **`crews.json` stores fingerprints only.** Non-reversible — never plaintext secrets.
- **CI secret scan.** `scripts/security_scan.py` runs in CI and fails on likely committed secrets.

To rotate `GA_API_KEY`: `./install.sh --api-key <new-key>`.

---

## Transport security

`SecurityHeadersMiddleware` emits `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, CSP with per-request nonce, and HSTS (`max-age` two years) on every response. HTTPS redirect is handled by Caddy. Minimum TLS is 1.2.

`security.validate_str` validates type, length, and format server-side. All `auth_kv` access uses parameterised SQL.

---

## Dashboard session auth

Dashboard ports are session-gated via Portal (Caddy). See [portal.md](portal.md) for setup. `gs_session` cookies have a configurable TTL (`GA_PORTAL_SESSION_TTL_SECS`, default 24 h) and are in-memory — they reset on transport restart.
