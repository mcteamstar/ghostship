# Auth

`ga-kiro-auth` is the reusable kiro-cli `auth_kv` payload (base64-encoded
JSON). It is stored as a single plain file, `DATA_DIR/ga-kiro-auth`, mode
`0600` — not a Podman secret. `DATA_DIR` is already bind-mounted read/write
into `ga-transport` (as `/data`), so transport reads and writes it directly;
`install.sh` doesn't need to touch it at all.

## Headless / API key auth (Pro+)

For headless / CI environments and Pro+ users with a kiro-cli API key, the
interactive device-code flow can be skipped entirely. Set `KIRO_API_KEY` and no
`POST /login` step is required.

**How it works**

1. Put your key in `ghostship.conf`:

   ```bash
   cp config/ghostship.conf.example config/ghostship.conf
   # Edit config/ghostship.conf:
   KIRO_API_KEY="<your-api-key>"
   ```

2. Re-run the installer so the transport picks up the new env var:

   ```bash
   ./install.sh --config config/ghostship.conf
   ```

3. Launch crews directly — **no `POST /login`, no browser step**:

   ```bash
   # launch succeeds immediately; the auth guard is bypassed
   ```

When `KIRO_API_KEY` is set:

- `launch` does **not** call `_initiate_login()` and does **not** require the
  `ga-kiro-auth` file to exist.
- The key is injected as a `KIRO_API_KEY` env var into each crew container at
  creation time; kiro-cli inside the crew authenticates directly from that env
  var.
- The `ga-kiro-auth` SQLite auth-row injection (`inject_auth.py`) is skipped —
  the env var replaces it.

> **Builder ID / device-code flow is unchanged when `KIRO_API_KEY` is unset.**
> Leaving `KIRO_API_KEY` empty (the default) keeps the existing device-code path
> in place exactly as described in **First login** below — `ga-kiro-auth`,
> `POST /login`, and `inject_auth.py` all behave as before. Free-tier / Builder
> ID users are unaffected.

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

> **Route reference:** For the authoritative list of all transport HTTP routes and their auth requirements, fetch `GET /openapi.json` (no auth required) from the running transport. The schema is generated at startup from the live route table.

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

When a crew is launched, the transport generates an **Ed25519 keypair**
(`Ed25519PrivateKey.generate()`). The **private seed** (hex-encoded raw 32-byte
seed) is persisted host-side only — read by `captain.py` to sign standing
orders — and is never placed inside the crew container. The **public key** is
delivered into the container as a **Podman secret** named
`admiral-pubkey-<crew_id>`, mounted read-only, root-owned, mode `0444` at
`/run/secrets/.admiral_public_key`. Every standing order the
transport writes to `/var/mail/captain` includes an `X-Admiral-Sig:` header —
a base64url-encoded Ed25519 signature of the message body produced with the
host-side private seed. Raven can invoke `/usr/local/bin/verify-admiral-sig`
to confirm a message is genuine before acting on it as a standing order; the
verifier loads the 32-byte public key from `.admiral_public_key`, base64url-
decodes the header, and calls `public_key.verify(sig, payload)`.

### Delivery path and threat model

The Admiral signing key is now split into a private/public pair — the private
half never enters the container, which is the core hardening over the previous
symmetric HMAC design (TRN-136):

1. **Private seed (host-side only)** — the hex-encoded Ed25519 private seed is
   persisted on the host via `_write_crew_secret` (mode `0600`, never stored in
   `crews.json`) and used exclusively by `captain.py` to sign standing orders.
   No copy of it exists inside the crew container, so no in-container process
   can forge an Admiral signature regardless of its privileges.

2. **Public key (`.admiral_public_key`, in-container)** — delivered as a Podman
   secret mounted **read-only, root-owned (uid/gid 0), mode `0444`**. A Podman
   secret can only be attached at `container_create` time, so the transport
   generates the keypair and calls `secret_create` *before* the create call.
   Because the mount is read-only **and** the container drops `CAP_SYS_ADMIN`
   (it cannot remount the filesystem read/write), `.admiral_public_key` is
   **immutable from inside the container** — an agent cannot overwrite it with
   a public key whose matching private key it controls. Verifying a signature
   requires only the public key, so no secret is exposed in-container at all.

   The mount point is `/run/secrets/`, deliberately **outside** the home and
   workspace volumes. Podman creates the intermediate directories for a secret
   target itself, owned by `root:root`, so a target under `/home/kirocrew` makes
   the crew's own config directory unwritable and the entrypoint dies before the
   gateway binds. `transport.constants.ADMIRAL_PUBKEY_PATH` and the `PUBKEY_PATH`
   constant in `verify-admiral-sig` hold this path and must change together.

**Threat model:** With an asymmetric keypair, reading `.admiral_public_key`
grants no forging capability — the public key verifies signatures but cannot
produce them, and the private seed is never in the container. This closes the
symmetric-secret exposure risk of the prior HMAC scheme entirely. The
**residual risk is replay**: a previously issued, correctly signed standing
order can be re-delivered verbatim and will still verify, because the signature
covers only the message body and carries no nonce or timestamp binding. Raven
must therefore treat standing-order *content* and ordering as it always has;
signature validity proves authenticity of origin, not freshness.

A separate `policy_signing_key` (a random 32-byte hex secret) is
generated at crew creation and used exclusively for policy signing:

3. **`admission_policy.json` `trust_keys` field** — required by KiroCrew's
   governance API to verify the security policy signature on gateway startup.
   This file is mode `0600` but is readable by agent processes running as the
   `kirocrew` user inside the container. It contains only `policy_signing_key`,
   never the Admiral private seed, so an agent that reads it cannot forge
   Admiral standing orders.

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
separate from the Admiral signing key — and the Admiral private seed never
enters the container at all — agent-readable `admission_policy.json` cannot be
used to forge Admiral standing orders (see TRN-53, TRN-136).

### Upgrade note (operators)

TRN-136 replaces the previous symmetric HMAC Admiral-signing scheme
(`.admiral_secret` + `admiral_secret`) with an Ed25519 keypair delivered via a
read-only Podman secret (`.admiral_public_key`). **Existing crews are not
migrated in place.** A Podman secret can only be attached at
`container_create` time, so a transport restart or a crew *restart* does not
give a running crew the new public-key mount, and a crew launched under the old
scheme still has `.admiral_secret` (not `.admiral_public_key`) on its home
volume. To adopt Ed25519 signing, an existing crew must be **nuked and
relaunched** — the relaunch generates a fresh keypair and mounts the public key
correctly. Until then, standing orders signed by the upgraded transport (now
Ed25519, base64url) will not verify against an old crew's HMAC verifier, so
plan the nuke/relaunch as part of the upgrade rather than expecting a rolling
restart to suffice.

### Storage

After the Admiral keypair and `policy_signing_key` are established for the crew,
`crews.json` stores only a non-reversible identifier for each secret
rather than the plaintext value. The identifiers use the scheme
`"sha256:<hex[:16]>"` (a SHA-256 digest of the secret, truncated to 64 bits
and prefixed with a label). These identifiers are sufficient for log correlation
("which crew used this secret fingerprint?") but cannot be used to replay or
derive the original secrets. The **Admiral Ed25519 private seed** (hex-encoded)
is additionally persisted (mode `0600`) to `DATA_DIR/secrets/<crew_id>` so the
transport can sign Captain standing orders after launch — but it is never stored
in `crews.json` and is never delivered into the crew container (only the public
key is, as a read-only Podman secret). The `policy_signing_key` plaintext is not
persisted to disk on the host at all beyond the in-container
`admission_policy.json`; only its identifier reaches the registry.

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
  `trust_keys` field (a hard dependency of the governance API). The container
  holds only the Admiral **public** key (`.admiral_public_key`, mounted
  read-only); the Ed25519 private seed used to sign standing orders never
  enters the container (TRN-136). An agent that reads any in-container file can
  therefore no longer forge Admiral standing orders; it can only forge security
  policy signatures, which is a lower-impact capability in the current
  single-operator, isolated-container use case.

## Dashboard session auth (Caddy / Portal mode)

When the Caddy reverse proxy is enabled, dashboard ports are protected by a session cookie gate instead of being unauthenticated. See [caddy.md](caddy.md) for setup.

### Auth flow overview

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

Three new HTTP routes on the main transport port (64057):

**`GET /dashboard/login`** — Serves the HTML login form. Accepts an optional `?next=<url>` query parameter for post-login redirect. Publicly accessible (no auth).

**`POST /dashboard/login`** — Accepts a `ga_api_key` form field. If it matches `GA_API_KEY` (constant-time comparison), issues a `gs_session` cookie and returns 200. Returns 401 on mismatch or when `GA_API_KEY` is not set. Cookie attributes: `HttpOnly; SameSite=Lax; Secure; Path=/`.

**`GET /dashboard/auth`** — Caddy's `forward_auth` target. Validates the `gs_session` cookie from the incoming request. On a valid session:
- Returns 200.
- If the request includes a `?port=<N>` parameter (as configured in the Caddy `forward_auth` URI), looks up the crew mapped to that port and returns `X-Crew-Cookie: mc_token_5476=<crew_token>`. Caddy's `copy_headers` directive carries this into the upstream request, authenticating the browser to the crew gateway.
- Returns 200 without the `X-Crew-Cookie` header if the port is unknown (session still valid; crew cookie injection is best-effort).

Returns 401 if the session is missing, invalid, or expired.

### `gs_session` cookie lifecycle

| Step | Event |
|:-----|:------|
| Issued | Operator submits valid `GA_API_KEY` to `POST /dashboard/login` |
| Stored | In-memory `dict[token → expiry]` in the transport process |
| TTL | `GA_PORTAL_SESSION_TTL_SECS` (default 86400 = 24 h) |
| Validated | On every request to a Caddy-gated dashboard port, via `forward_auth` call to `/dashboard/auth` |
| Purged | On expiry check, or on transport restart (in-memory only) |
| Rotated | Log out and log back in via `/dashboard/login` |

Sessions are single-process, in-memory. A transport restart clears all sessions — users must log in again. The session store has no persistence, database, or shared state.

### Bearer enforcement at the edge

When `GA_API_KEY` is set (Portal is always active):

- `/mcp*` and `/files/*` routes on Caddy's main port (443) require `Authorization: Bearer <GA_API_KEY>`. Caddy rejects bad or missing tokens before the request reaches the transport.
- The transport's own `BearerAuthMiddleware` remains active as a defence-in-depth layer.
- `/dashboard/auth`, `/dashboard/login`, and `/dashboard/logout` are public routes — they are exempt from the Bearer check (auth is the point of those endpoints).

### Auth posture summary

| | Current (Portal always active) |
|:--|:--|
| MCP / files | Caddy rejects bad Bearer at the edge; `BearerAuthMiddleware` is defence-in-depth |
| Dashboard ports | `forward_auth` → `gs_session` cookie gate on every port |
| TLS | Caddy-terminated on all ports (`GA_PORTAL_TLS_MODE`) |
| Auth upgrade to SSO | Caddy-config change only (swap `forward_auth` → `caddy-security`) |
