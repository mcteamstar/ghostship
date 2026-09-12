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

**Recommended flow: `POST /login` → open URL → confirm complete → `launch`.**

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

## MCP API-key authentication (`GA_API_KEY`)

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

The `ghostship auth` subcommand group drives the device auth flow directly from
the CLI — useful for re-authenticating after a token expires, switching
identity, or on a fresh install without an agent client.

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
