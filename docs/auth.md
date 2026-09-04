# Auth

`ga-kiro-auth` is the reusable kiro-cli `auth_kv` payload (base64-encoded
JSON). It is stored as a single plain file, `DATA_DIR/ga-kiro-auth`, mode
`0600` — not a Podman secret. `DATA_DIR` is already bind-mounted read/write
into `ga-transport` (as `/data`), so transport reads and writes it directly;
`install.sh` doesn't need to touch it at all.

## First login

Auth must be completed before `launch` will work. If you attempt to launch a crew without completing auth first, the launch will fail — **do not retry `launch` until auth is confirmed complete**, as any crew created mid-auth will be unauthenticated and must be nuked.

The recommended flow is always: **`POST /login` → open URL → confirm complete → then `launch`**.

### Step-by-step first-login walkthrough

**1. Run install with your identity provider settings**

For IAM Identity Center (org-licensed) installs, pass all three flags — or put them in a config file (recommended):

```bash
# Flags directly:
./install.sh \
  --identity-provider https://d-xxxxxxxxxx.awsapps.com/start/#/ \
  --region <region> \
  --license pro

# Or via config file (recommended for repeatability):
cp config/ghostship.conf.example config/ghostship.conf
# Edit config/ghostship.conf, then:
./install.sh --config config/ghostship.conf
```

Key points:
- The start URL **must include the `/#/` suffix** — e.g. `https://d-xxxxxxxxxx.awsapps.com/start/#/`. Without it, the login flow will not route through your IdC correctly.
- `--license pro` is required for IAM Identity Center. Without it, kiro-cli falls back to Builder ID (free tier).
- **WSL2 users:** ghostship is verified on WSL2. The installer detects WSL2 automatically and applies the required `iptables` networking workaround — no manual steps needed.

**2. Trigger the login flow**

After install completes, call `POST /login`:

```bash
curl -sX POST http://localhost:64057/login | jq
```

Response:
```json
{
  "status": "pending",
  "login_url": "https://d-xxxxxxxxxx.awsapps.com/start/#/device?user_code=XXXX-XXXX",
  "code": "XXXX-XXXX"
}
```

The `login_url` will go through your Identity Center (not the generic `view.awsapps.com`) when `KIRO_IDENTITY_PROVIDER` is set correctly.

**3. Open the URL and approve the device**

Open `login_url` in a browser and sign in with your org credentials. The device code is embedded in the URL — you may be asked to confirm it.

**4. Confirm the flow completed**

Poll `GET /login` until it returns `complete`:

```bash
curl -s http://localhost:64057/login | jq .status
# → "complete"
```

**5. Launch your first crew**

Only after seeing `"complete"` should you launch:

```bash
# Via MCP tool:
ghostship__launch(crew_id="general")

# Or register the MCP server first if you haven't yet:
kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
```

**Known UX limitation:** attempting `launch` before auth is complete will fail with `not_authenticated`. Any crew that was partially created in this state must be nuked (`ghostship__nuke(crew_id=..., confirm=True)`) before re-launching — it cannot be salvaged. Always complete the `POST /login` flow before your first `launch`.

---

On first launch (no auth file yet, or it's empty): the transport reads the
auth credentials written by `POST /login` and injects them into the crew
container. `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` control which identity
provider that login targets — without them, kiro-cli falls back to Builder ID
(free tier), which is unlikely to be what an org-licensed install wants.

**Note for `--license pro` (IAM Identity Center) operators:** the `launch`
first-time auth path uses a non-TTY exec that may fail silently for the IDC
device flow (upstream bug [#6120](https://github.com/kirodotdev/Kiro/issues/6120)).
Use the `POST /login` endpoint above for initial auth instead.

When the flow completes, the transport writes the auth file in place,
flushes it, and restores mode `0600` or stricter. If the file is missing or
empty, launch falls back to auth rows from a currently running crew; if no
reusable rows are available, the normal device-auth path remains available.

## Identity provider config

Resolved in this order:

1. `--config <path>` — a shell file exporting `KIRO_IDENTITY_PROVIDER`,
   `KIRO_REGION`, `KIRO_LICENSE`
2. `--identity-provider` / `--region` / `--license` flags on `install.sh`
3. Interactive prompt, if running in a terminal and still unset

Because the config file is sourced *before* flag parsing, explicit flags
always win. This lets teams share a single config file while individual
operators override one value on the command line.

### Example config file (identity provider only)

```bash
# idp.conf — identity settings for our org
KIRO_IDENTITY_PROVIDER="https://identitycenter.amazonaws.com/ssoins-abc123"
KIRO_REGION="us-east-1"
KIRO_LICENSE="pro"
```

Usage:

```bash
./install.sh --config ./idp.conf
# Or override region for a test:
./install.sh --config ./idp.conf --region us-west-2
```

See [configuration.md](configuration.md#config-file) for the full list of
supported variables and resolution semantics.

## Uninstall retention

Ordinary `uninstall.sh` removes the registry and other transport state but
keeps `DATA_DIR/ga-kiro-auth`, so a later install can reuse the login.
`uninstall.sh --purge-auth` removes it too and requires a fresh device-auth
login on the next install.

On Linux with a dedicated instance, omitting `--keep-machine` removes only the
dedicated Podman storage root (`containers/`) — not `ga-kiro-auth`. The
`--purge-auth` flag is the sole control over whether credentials are removed,
independent of `--keep-machine`.

## Secret rotation

When tokens expire, use the login/logout endpoints below to re-authenticate
without nuking any crews: `POST /logout` to clear the stale auth, then
`POST /login` to get fresh tokens. Running crews get fresh auth injected
immediately on `GET /login` completing — no nuke or relaunch needed.

## Operator login / logout API

The transport exposes three HTTP endpoints on the MCP port for managing
academy-wide kiro-cli authentication. These are **not** MCP tools — agents
cannot call them. They are plain HTTP routes that require the same
`Authorization: Bearer <key>` header as all other routes when `GA_API_KEY`
is set.

### Academy auth state machine

```
UNAUTHENTICATED  ──[POST /login]──►  PENDING  ──[GET /login → complete]──►  AUTHENTICATED
                                                                                    │
                ◄──────────────────────────────────[POST /logout]──────────────────┘
```

`ga-kiro-auth` is the source of truth: present and non-empty = authenticated,
absent or empty = not. A transport restart mid-login clears pending state; any
`ga-login-*` containers left over are swept on startup.

### POST /login — initiate device auth

Starts the kiro-cli device auth flow inside a dedicated ephemeral container.
Returns the browser URL and device code immediately. The flow runs in the
background until the browser redirect completes.

**Guards:** returns `409` if already authenticated (call `POST /logout` first)
or if a login is already in progress (poll `GET /login`).

```bash
# Without API key:
curl -sX POST http://localhost:64057/login | jq

# With API key:
curl -sX POST http://localhost:64057/login \
  -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq
```

Response:
```json
{
  "status": "pending",
  "login_url": "https://device.sso.us-east-1.amazonaws.com/...",
  "code": "BCDF-GHJK"
}
```

Open `login_url` in a browser and complete the sign-in. Then poll:

### GET /login — poll completion

Checks whether the device auth has completed. On success: writes
`ga-kiro-auth`, injects fresh auth into all currently running crews, nukes
the ephemeral container, and returns `complete`.

Returns `404` if no login flow is in progress.

```bash
# Poll until complete (typically a few seconds after browser sign-in):
watch -n 2 'curl -s http://localhost:64057/login | jq .status'

# With API key:
curl -s http://localhost:64057/login \
  -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq
```

Response when done:
```json
{ "status": "complete" }
```

After `complete`, all future `launch` calls inject the new auth automatically.
Running crews also have their auth updated in-place — no restart needed.

### POST /logout — de-authenticate the academy

Deletes `ga-kiro-auth` and clears `auth_kv` rows from every running crew's
kiro-cli DB. Future `launch` calls and agent dispatches will fail auth until
`POST /login` is completed again.

Returns `404` if not authenticated.

```bash
curl -sX POST http://localhost:64057/logout | jq

# With API key:
curl -sX POST http://localhost:64057/logout \
  -H "Authorization: Bearer $GHOSTSHIP_API_KEY" | jq
```

Response:
```json
{ "status": "logged_out" }
```

## MCP API-key authentication (`GA_API_KEY`)

An optional static bearer credential that protects the MCP endpoint. When
set, the transport requires `Authorization: Bearer <key>` on every HTTP
request to the MCP listener. Missing, malformed, duplicated, or incorrect
credentials are rejected with `401 Unauthorized` + `WWW-Authenticate: Bearer`
before any MCP processing occurs.

This is a shared secret, not OAuth — there is no identity, scope, or token
exchange. It is compared using `hmac.compare_digest` (constant-time) and is
never logged, printed, or included in responses.

### Enabling

```bash
./install.sh --api-key <your-secret-key>
# OR set GA_API_KEY=<key> in a config file and pass --config <path>
```

`install.sh` persists the key to a plain, mode-`0600` file in your data
directory (`DATA_DIR/ga-api-key`). Once set, later `./install.sh` runs reuse
it automatically — you don't need to pass `--api-key` every time. The install
output reports only `enabled` / `disabled`, never the key itself.

#### How the key is stored and delivered

The key is delivered to the transport container as a **Podman secret**
(not an environment variable). `install.sh` runs:

```bash
podman secret rm ga-api-key 2>/dev/null || true
printf '%s' "$GA_API_KEY" | podman secret create ga-api-key -
```

The container is started with `--secret ga-api-key`, which bind-mounts the
key read-only at `/run/secrets/ga-api-key` inside the container. The
transport reads it from that path at startup. This approach means the key
**never appears** in `podman inspect`, `/proc/1/environ`, or any other
process-metadata surface.

The persisted file in `DATA_DIR/ga-api-key` is the source of truth across
installs — the Podman secret is recreated from it on each `install.sh` run.

#### Rotating the API key

1. Run `./install.sh --api-key <new-key>` — this overwrites the persisted
   file, recreates the Podman secret, and restarts the transport container.
2. Update all MCP clients with the new bearer token.

No downtime is required beyond the container restart (~2s).

### Client configuration

After enabling, add the bearer header to each MCP client. See the
[Connecting to a harness](../README.md#connecting-to-a-harness) section in
the README for kiro-cli and Claude Code examples with the `Authorization`
header.

### Relationship to file-transfer HMAC

`GA_API_KEY` protects the MCP endpoint only. File-transfer routes share the
same port but use HMAC presigned URLs for authorization — a valid presigned
URL issued by `evac` or `supply` (which are MCP tools and therefore
API-key-protected at issuance) remains usable via plain `curl` without an
additional header until its TTL expires.

### Rollback

Because the key persists, simply omitting `--api-key` on a later install does
**not** disable it. To actually turn it off, run `./install.sh --api-key ""`
(empty value) — this clears the persisted file and disables the check on
restart. No data migration is required. Remove the header from client
configs if desired.

### Security notes

- Plain HTTP is appropriate only for loopback (`127.0.0.1`) or a trusted
  private tunnel. For remote deployments, terminate TLS at a reverse proxy
  or route through an encrypted VPN.
- The key is delivered via Podman secret (`--secret ga-api-key`), mounted
  read-only at `/run/secrets/ga-api-key`. It is **not** visible via
  `podman inspect` or `/proc/1/environ`.
- The persisted file in `DATA_DIR/ga-api-key` (mode `0600`) is accessible
  only to the user running `install.sh`. Ensure `~/.local/share/containers/`
  is mode `0700` on multi-user systems.
- Automatic key generation and rotation are intentionally out of scope.

## Admiral mail signing (`admiral_secret`)

When a crew is launched, the transport generates a random 32-byte hex secret
(`admiral_secret`) and injects it into the crew container at
`/home/kirocrew/.kiro/crew/.admiral_secret` (mode `0600`). Every standing order
the transport writes to `/var/mail/captain` includes an `X-Admiral-Sig:` header
— an HMAC-SHA256 signature of the message body keyed by this secret. Raven can
invoke `/usr/local/bin/verify-admiral-sig` to confirm a message is genuine
before acting on it as a standing order.

### Delivery path and threat model

The `admiral_secret` is written to one place:

1. **`.admiral_secret` file** (mode `0600`) — read by `verify-admiral-sig` to
   verify Admiral mail signatures. This file is readable only by the
   `kirocrew` user inside the container. The secret is delivered to the
   injection script over **stdin** (TRN-93), never as a `podman exec`
   argument, so it never appears in the exec argument list or in
   `/proc/<pid>/cmdline` on the host.

A separate `policy_signing_key` (also a random 32-byte hex secret) is
generated at crew creation and used exclusively for policy signing:

2. **`admission_policy.json` `trust_keys` field** — required by KiroCrew's
   governance API to verify the security policy signature on gateway startup.
   This file is mode `0600` but is readable by agent processes running as the
   `kirocrew` user inside the container. Because it contains `policy_signing_key`
   (not `admiral_secret`), an agent that reads it can no longer extract the
   Admiral mail-signing secret and forge standing orders.

**Threat model:** An agent that reads `admission_policy.json` can extract the
`policy_signing_key` and forge security policy signatures, but it cannot forge
Admiral standing orders — those require `admiral_secret`, which is only
accessible via the `.admiral_secret` file. This separation closes the
previously accepted risk noted in TRN-38. For multi-operator or
untrusted-agent deployments, storing `policy_signing_key` in
`admission_policy.json` (which any `kirocrew`-user process can read) is
still an accepted risk for the current isolated-container use case.

### Policy signing

A dedicated `policy_signing_key` (distinct from `admiral_secret`) is used to
sign the crew's security policy at injection time. The transport computes
HMAC-SHA256 over the canonical (sorted-keys JSON) policy body and writes the
signature into `~/.kiro/crew/security_policy.json` as `identity.signature`.
The gateway verifies this signature on load; a tampered `security_policy.json`
causes a mismatch and the gateway refuses to continue — an agent cannot forge a
valid policy without the `policy_signing_key`.

`admission_policy.json` carries the `policy_signing_key` in its `trust_keys`
field — this is required by KiroCrew's governance API, which reads trust keys
from the policy file at gateway startup. Because `policy_signing_key` is
separate from `admiral_secret`, agent-readable `admission_policy.json` no
longer exposes the Admiral mail-signing secret (see TRN-53).

### Storage

After `admiral_secret` and `policy_signing_key` are injected into the crew
container, `crews.json` stores only a non-reversible identifier for each secret
rather than the plaintext value. The identifiers use the scheme
`"sha256:<hex[:16]>"` (a SHA-256 digest of the secret, truncated to 64 bits
and prefixed with a label). These identifiers are sufficient for log correlation
("which crew used this secret fingerprint?") but cannot be used to replay or
derive the original secrets. The `admiral_secret` plaintext is additionally
persisted (mode `0600`) to `DATA_DIR/secrets/<crew_id>` so the transport can
sign Captain standing orders after launch — but it is never stored in
`crews.json`. The `policy_signing_key` plaintext is not persisted to disk on
the host at all beyond the in-container `admission_policy.json`; only its
identifier reaches the registry.

`policy_signing_key_id` is only written to the registry when policy injection
succeeds.

### Threat model

- **Single operator (local):** `DATA_DIR` is only accessible to the user
  running the transport container. The threat model is the same as for
  `GA_API_KEY` — operator-level access to the host is assumed trusted. No
  additional hardening is required.
- **Multi-operator:** If multiple operators share access to the host's data
  volume (or can run `podman inspect ga-transport`), they can read the
  identifier fingerprints from `crews.json`, but these are non-reversible and
  cannot be used to forge Admiral standing orders or policy signatures. For
  multi-operator deployments, `DATA_DIR` should have `0700` permissions and
  `podman inspect` access should be restricted.
- **Agent-level isolation:** Agent processes inside the crew container can
  read `admission_policy.json`, which carries `policy_signing_key` in its
  `trust_keys` field (a hard dependency of the governance API). As of TRN-53,
  `admission_policy.json` no longer contains `admiral_secret` — the two
  secrets are now distinct. An agent that reads the file can no longer forge
  Admiral standing orders; it can only forge security policy signatures, which
  is a lower-impact capability in the current single-operator, isolated-container
  use case.

## Dashboard session auth (Caddy mode, `GA_PORTSIDE_ENABLED=true`)

When the Caddy reverse proxy is enabled, dashboard ports are protected by a session cookie gate instead of being unauthenticated. See [caddy.md](caddy.md) for setup.

### Auth flow overview

```
Browser ──GET :64058/──▶ ga-portside
                            │
                            ├─ forward_auth ──GET /dashboard-auth──▶ ga-transport
                            │                 valid gs_session?
                            │                 ├─ YES → 200 + X-Crew-Cookie header
                            │                 └─ NO  → 401 → Caddy → redirect to /login-ui
                            │
                            └─ (on 200) reverse_proxy ──▶ gs-{crew_id}:5476
                                         X-Crew-Cookie injected as cookie
```

### Dashboard endpoints

Three new HTTP routes on the main transport port (64057):

**`GET /login-ui`** — Serves the HTML login form. Accepts an optional `?next=<url>` query parameter for post-login redirect. Publicly accessible (no auth).

**`POST /dashboard-login`** — Accepts a `ga_api_key` form field. If it matches `GA_API_KEY` (constant-time comparison), issues a `gs_session` cookie and returns 200. Returns 401 on mismatch or when `GA_API_KEY` is not set. Cookie attributes: `HttpOnly; SameSite=Lax; Secure; Path=/`.

**`GET /dashboard-auth`** — Caddy's `forward_auth` target. Validates the `gs_session` cookie from the incoming request. On a valid session:
- Returns 200.
- If the request includes a `?port=<N>` parameter (as configured in the Caddy `forward_auth` URI), looks up the crew mapped to that port and returns `X-Crew-Cookie: mc_token_5476=<crew_token>`. Caddy's `copy_headers` directive carries this into the upstream request, authenticating the browser to the crew gateway.
- Returns 200 without the `X-Crew-Cookie` header if the port is unknown (session still valid; crew cookie injection is best-effort).

Returns 401 if the session is missing, invalid, or expired.

### `gs_session` cookie lifecycle

| Step | Event |
|:-----|:------|
| Issued | Operator submits valid `GA_API_KEY` to `POST /dashboard-login` |
| Stored | In-memory `dict[token → expiry]` in the transport process |
| TTL | `GA_PORTSIDE_SESSION_TTL_SECS` (default 86400 = 24 h) |
| Validated | On every request to a Caddy-gated dashboard port, via `forward_auth` call to `/dashboard-auth` |
| Purged | On expiry check, or on transport restart (in-memory only) |
| Rotated | Log out and log back in via `/login-ui` |

Sessions are single-process, in-memory. A transport restart clears all sessions — users must log in again. The session store has no persistence, database, or shared state.

### Bearer enforcement at the edge

When `GA_PORTSIDE_ENABLED=true` and `GA_API_KEY` is set:

- `/mcp*` and `/files/*` routes on Caddy's main port (443) require `Authorization: Bearer <GA_API_KEY>`. Caddy rejects bad or missing tokens before the request reaches the transport.
- The transport's own `BearerAuthMiddleware` remains active as a defence-in-depth layer.
- `/dashboard-auth`, `/login-ui`, and `/dashboard-login` are public routes — they are exempt from the Bearer check (auth is the point of those endpoints).

### Auth posture summary

| | `GA_PORTSIDE_ENABLED=false` | `GA_PORTSIDE_ENABLED=true` |
|:--|:--|:--|
| MCP / files | `BearerAuthMiddleware` when `GA_API_KEY` set | Caddy rejects bad Bearer at the edge; `BearerAuthMiddleware` is defence-in-depth |
| Dashboard ports | **Unauthenticated** — network-layer only (Tailscale/firewall) | `forward_auth` → `gs_session` cookie gate on every port |
| TLS | None, or direct `GA_TLS_*` | Caddy-terminated on all ports (`GA_PORTSIDE_TLS_MODE`) |
| Auth upgrade to SSO | Requires transport code changes | Caddy-config change only (swap `forward_auth` → `caddy-security`) |
