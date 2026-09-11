# Auth

`ga-kiro-auth` is the kiro-cli `auth_kv` payload (base64-encoded JSON), stored at
`DATA_DIR/ga-kiro-auth` (mode `0600`). `DATA_DIR` is bind-mounted read/write into
`ga-transport` as `/data`.

## Headless / API key auth (Pro+)

For CI or Pro+ users with a kiro-cli API key, skip the device-code flow entirely.

```bash
cp config/ghostship.conf.example config/ghostship.conf
# Set KIRO_API_KEY="<your-api-key>" in ghostship.conf, then:
./install.sh --config config/ghostship.conf
```

When `KIRO_API_KEY` is set, `launch` skips `_initiate_login()`, the key is injected
as `KIRO_API_KEY` into each crew container, and the `inject_auth.py` SQLite step is
skipped. Leaving it empty keeps the device-code path for free-tier / Builder ID users.

## First login

Complete auth before calling `launch`. Any crew created before auth completes is
unauthenticated and cannot be salvaged — nuke it.

**Recommended flow: `POST /login` → open URL → confirm complete → `launch`.**

### Step-by-step

**1. Install with identity provider settings**

```bash
# Via config file (recommended):
cp config/ghostship.conf.example config/ghostship.conf
./install.sh --config config/ghostship.conf

# Or inline:
./install.sh \
  --identity-provider https://d-xxxxxxxxxx.awsapps.com/start/#/ \
  --region <region> \
  --license pro
```

- The start URL **must include `/#/`**.
- `--license pro` is required for IAM Identity Center; without it kiro-cli falls back to Builder ID.
- WSL2 is supported; the installer detects it and applies the required `iptables` workaround.

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

**5. Launch**

```bash
ghostship__launch(crew_id="general")
# Or register first:
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
```

> **`--license pro` operators:** the non-TTY exec path used by `launch` may fail
> silently for IdC device flow (upstream [#6120](https://github.com/kirodotdev/Kiro/issues/6120)).
> Use `POST /login` for initial auth.

## Identity provider config

Resolved in order:

1. `--config <path>` — shell file exporting `KIRO_IDENTITY_PROVIDER`, `KIRO_REGION`, `KIRO_LICENSE`
2. `--identity-provider` / `--region` / `--license` flags on `install.sh`
3. Interactive prompt (terminal only)

Explicit flags always win over the config file.

```bash
# idp.conf
KIRO_IDENTITY_PROVIDER="https://identitycenter.amazonaws.com/ssoins-abc123"
KIRO_REGION="us-east-1"
KIRO_LICENSE="pro"
```

```bash
./install.sh --config ./idp.conf
./install.sh --config ./idp.conf --region us-west-2  # override one value
```

See [configuration.md](configuration.md#config-file) for all supported variables.

## Uninstall retention

`uninstall.sh` removes transport state but keeps `ga-kiro-auth` so a later install
can reuse the login. Pass `--purge-auth` to remove it too and require a fresh
device-auth login. On Linux, `--purge-auth` is the sole control over credential
removal — independent of `--keep-machine`.

## Secret rotation

When tokens expire: `POST /logout` to clear stale auth, then `POST /login` for
fresh tokens. Running crews receive fresh auth immediately — no nuke or relaunch needed.

## Operator login / logout API

Three HTTP endpoints on the MCP port for managing academy-wide kiro-cli auth.
These are **not** MCP tools — agents cannot call them. They require
`Authorization: Bearer <key>` when `GA_API_KEY` is set. For the authoritative
route list, fetch `GET /openapi.json` (no auth required).

### Auth state machine

```
UNAUTHENTICATED  ──[POST /login]──►  PENDING  ──[GET /login → complete]──►  AUTHENTICATED
                                                                                    │
                ◄──────────────────────────────────[POST /logout]──────────────────┘
```

`ga-kiro-auth` is the source of truth: present and non-empty = authenticated.
A transport restart mid-login clears pending state; leftover `ga-login-*` containers
are swept on startup.

### POST /login — initiate device auth

Starts the kiro-cli device auth flow in an ephemeral container and returns the browser
URL and device code. Returns `409` if already authenticated or a login is in progress.

```bash
curl -sX POST http://localhost:64057/login | jq
curl -sX POST http://localhost:64057/login -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq
```

```json
{ "status": "pending", "login_url": "https://device.sso.us-east-1.amazonaws.com/...", "code": "BCDF-GHJK" }
```

### GET /login — poll completion

On success: writes `ga-kiro-auth`, injects fresh auth into all running crews, nukes
the ephemeral container, returns `complete`. Returns `404` if no login is in progress.

```bash
watch -n 2 'curl -s http://localhost:64057/login | jq .status'
```

```json
{ "status": "complete" }
```

### POST /logout — de-authenticate

Deletes `ga-kiro-auth` and clears `auth_kv` rows from every running crew. Returns
`404` if not authenticated.

```bash
curl -sX POST http://localhost:64057/logout | jq
```

```json
{ "status": "logged_out" }
```

## MCP API-key authentication (`GA_API_KEY`)

An optional static bearer credential protecting the MCP endpoint. When set, every
HTTP request to the MCP listener must carry `Authorization: Bearer <key>`. Bad or
missing credentials are rejected with `401 Unauthorized` before any MCP processing.
Compared using `hmac.compare_digest`; never logged.

### Enabling

```bash
./install.sh --api-key <your-secret-key>
# Or set GA_API_KEY in a config file and pass --config <path>
```

The key is persisted to `DATA_DIR/ga-api-key` (mode `0600`) and reused on subsequent
installs — you don't need to pass `--api-key` every time. Install output reports
`enabled` / `disabled`, never the key value.

### Storage and delivery

The key is delivered to the transport container as a **Podman secret** — never as an
environment variable. `install.sh` creates the secret; the container mounts it
read-only at `/run/secrets/ga-api-key`. The key never appears in `podman inspect` or
`/proc/1/environ`. `DATA_DIR/ga-api-key` is the source of truth; the Podman secret is
recreated from it on each `install.sh` run.

### Rotating

```bash
./install.sh --api-key <new-key>   # rewrites file, recreates secret, restarts transport (~2s)
```

Update all MCP clients with the new bearer token.

### Client configuration

See [Connecting to a harness](../README.md#connecting-to-a-harness) for kiro-cli and
Claude Code examples with the `Authorization` header.

### Relationship to file-transfer HMAC

`GA_API_KEY` protects the MCP endpoint only. File-transfer routes on the same port use
HMAC presigned URLs — a valid presigned URL (issued by the API-key-protected `evac`/
`supply` tools) is usable via plain `curl` until its TTL expires.

### Disabling

Omitting `--api-key` on a later install does **not** disable it. To turn it off:
`./install.sh --api-key ""` — this clears the persisted file and disables the check on restart.

### Security notes

- Plain HTTP is appropriate only for loopback (`127.0.0.1`) or a trusted private tunnel.
  For remote deployments, terminate TLS at a reverse proxy or use an encrypted VPN.
- `DATA_DIR/ga-api-key` is mode `0600`. Ensure `~/.local/share/containers/` is mode `0700`
  on multi-user systems.

## Admiral mail signing (`admiral_secret`)

At crew launch the transport generates an **Ed25519 keypair**. The private seed
(hex-encoded, 32 bytes) lives host-side only — used by `captain.py` to sign standing
orders — and never enters the crew container. The public key is delivered into the
container as a read-only, root-owned Podman secret (mode `0444`) at
`/run/secrets/.admiral_public_key`. Every standing order written to `/var/mail/captain`
carries an `X-Admiral-Sig:` header (base64url Ed25519 signature). Raven calls
`/usr/local/bin/verify-admiral-sig` to confirm authenticity before acting on an order.

### Delivery path and threat model

**Private seed (host-side only):** persisted via `_write_crew_secret` (mode `0600`),
never in `crews.json`, never delivered into the container. No in-container process can
forge an Admiral signature regardless of privileges.

**Public key (`.admiral_public_key`, in-container):** Podman secret, mounted read-only,
root-owned, mode `0444`. Because the container drops `CAP_SYS_ADMIN`, the mount is
immutable from inside. `transport.constants.ADMIRAL_PUBKEY_PATH` and `PUBKEY_PATH` in
`verify-admiral-sig` must be kept in sync.

**Residual risk — replay:** a correctly signed standing order can be re-delivered
verbatim and will still verify (the signature covers only the body; there is no nonce
or timestamp). Raven must evaluate content and ordering as always; signature validity
proves authenticity of origin, not freshness.

### Policy signing

A separate `policy_signing_key` (32-byte hex) is generated at crew creation and used to
sign `security_policy.json` via HMAC-SHA256 over the canonical sorted-keys JSON body.
The gateway verifies this signature on load; a tampered policy causes a mismatch and the
gateway refuses to start.

`admission_policy.json` carries `policy_signing_key` in its `trust_keys` field (required
by KiroCrew's governance API). Because `policy_signing_key` is distinct from the Admiral
seed — and the Admiral seed never enters the container — an agent reading
`admission_policy.json` cannot forge Admiral standing orders (see TRN-53, TRN-136).

### Storage

`crews.json` stores only a non-reversible `sha256:<hex[:16]>` identifier for each
secret — sufficient for log correlation, useless for replay. The Admiral Ed25519 private
seed is additionally persisted to `DATA_DIR/secrets/<crew_id>` (mode `0600`) so the
transport can sign standing orders after launch. `policy_signing_key` plaintext is not
persisted host-side; only its identifier reaches the registry, and only after successful
policy injection.

### Upgrade note (TRN-136)

TRN-136 replaces the previous symmetric HMAC scheme (`.admiral_secret`) with an Ed25519
keypair. **Existing crews are not migrated in place** — a Podman secret can only be
attached at `container_create` time. Standing orders signed by the upgraded transport
will not verify against an old crew's HMAC verifier. **Nuke and relaunch existing crews**
as part of the upgrade.

### Threat model summary

| Scope | Posture |
|:------|:--------|
| Single operator (local) | `DATA_DIR` accessible only to the transport user. Same posture as `GA_API_KEY`. |
| Multi-operator | `crews.json` fingerprints are non-reversible. Restrict `DATA_DIR` to mode `0700`; limit `podman inspect` access. |
| Agent-level | In-container `admission_policy.json` carries `policy_signing_key` but only the Admiral **public** key. An agent can forge security policy signatures but not Admiral standing orders (TRN-136). |

## Dashboard session auth (Caddy / Portal mode)

When the Caddy reverse proxy is enabled, dashboard ports are protected by a session
cookie gate. See [caddy.md](caddy.md) for setup.

### Auth flow

```
Browser ──GET :64058/──▶ ga-portal
                            │
                            ├─ forward_auth ──GET /dashboard/auth──▶ ga-transport
                            │                 valid gs_session?
                            │                 ├─ YES → 200 + X-Crew-Cookie header
                            │                 └─ NO  → 401 → Caddy → redirect to /dashboard/login
                            │
                            └─ (on 200) reverse_proxy ──▶ gs-{crew_id}:5476
                                         X-Crew-Cookie injected as cookie
```

### Dashboard endpoints

All on the main transport port (64057):

**`GET /dashboard/login`** — HTML login form. Accepts `?next=<url>` for post-login
redirect. Public (no auth required).

**`POST /dashboard/login`** — Accepts a `ga_api_key` form field. On match, issues a
`gs_session` cookie (HttpOnly; SameSite=Lax; Secure; Path=/) and returns 200. Returns
401 on mismatch or when `GA_API_KEY` is unset.

**`GET /dashboard/auth`** — Caddy's `forward_auth` target. Validates the `gs_session`
cookie. On valid session, returns 200 and (when `?port=<N>` is present) the
`X-Crew-Cookie` header for the mapped crew. Returns 200 without the crew cookie if the
port is unknown. Returns 401 on invalid or expired session.

### `gs_session` cookie lifecycle

| Event | Detail |
|:------|:-------|
| Issued | Valid `GA_API_KEY` submitted to `POST /dashboard/login` |
| Stored | In-memory `dict[token → expiry]`; cleared on transport restart |
| TTL | `GA_PORTAL_SESSION_TTL_SECS` (default 86400 s / 24 h) |
| Validated | On every request to a Caddy-gated port via `forward_auth` |
| Rotated | Log out and back in via `/dashboard/login` |

### Bearer enforcement at the edge

When `GA_API_KEY` is set:

- `/mcp*` and `/files/*` require `Authorization: Bearer <GA_API_KEY>` at the Caddy edge;
  `BearerAuthMiddleware` in the transport is defence-in-depth.
- `/dashboard/auth`, `/dashboard/login`, and `/dashboard/logout` are exempt.

### Auth posture summary

| Resource | Protection |
|:---------|:-----------|
| MCP / files | Caddy Bearer check + transport middleware (defence-in-depth) |
| Dashboard ports | `forward_auth` → `gs_session` cookie gate on every port |
| TLS | Caddy-terminated (`GA_PORTAL_TLS_MODE`) |
| Auth upgrade to SSO | Caddy-config change only (swap `forward_auth` → `caddy-security`) |
