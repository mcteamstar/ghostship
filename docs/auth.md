# Auth

`ga-kiro-auth` is the reusable kiro-cli `auth_kv` payload (base64-encoded
JSON). It is stored as a single plain file, `DATA_DIR/ga-kiro-auth`, mode
`0600` — not a Podman secret. `DATA_DIR` is already bind-mounted read/write
into `ga-transport` (as `/data`), so transport reads and writes it directly;
`install.sh` doesn't need to touch it at all.

## First login

On first launch (no auth file yet, or it's empty): initiates
`kiro-cli login --use-device-flow` inside the crew container and returns a
device auth URL. `KIRO_IDENTITY_PROVIDER` and `KIRO_REGION` control which
identity provider that login targets — without them, kiro-cli falls back to
Builder ID (free tier), which is unlikely to be what an org-licensed install
wants. After the user completes the flow, call launch again with the same
`crew_id` to save the auth file and finish setup.

**Note for `--license pro` (IAM Identity Center) operators:** the `launch`
first-time auth path uses a non-TTY exec that may fail silently for the IDC
device flow (upstream bug [#6120](https://github.com/kirodotdev/Kiro/issues/6120)).
Use the `POST /login` endpoint below for initial auth instead.

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

#### Deprecated: environment variable fallback

If `/run/secrets/ga-api-key` is not present (e.g. the operator upgraded the
transport image but has not yet re-run `install.sh`), the transport falls
back to reading `GA_API_KEY` from the environment and logs a deprecation
warning at startup. Re-run `install.sh` to migrate to the secrets-based
delivery. The env-var fallback will be removed in a future release.

### Client configuration

After enabling, add the bearer header to each MCP client:

**Kiro CLI / IDE:**
```bash
kiro-cli mcp add --name ghostship \
  --url http://localhost:64057/mcp \
  --headers '{"Authorization": "Bearer ${GHOSTSHIP_API_KEY}"}' \
  --scope global
```
Set `GHOSTSHIP_API_KEY` in your shell environment — do not commit the literal.

**Claude Code** (`~/.claude.json`):
```json
"ghostship": {
  "type": "http",
  "url": "http://localhost:64057/mcp",
  "headers": { "Authorization": "Bearer ${GHOSTSHIP_API_KEY}" }
}
```

**Generic streamable-HTTP clients:**
Send `Authorization: Bearer <key>` on initialization and every subsequent
MCP GET/POST/DELETE request.

### Relationship to file-transfer HMAC

`GA_API_KEY` protects the MCP endpoint only. The companion file server on
`PORT+1` retains its existing HMAC presigned-URL model — a valid presigned
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

The `admiral_secret` is written to two places:

1. **`.admiral_secret` file** (mode `0600`) — read by `verify-admiral-sig` to
   verify Admiral mail signatures.
2. **`admission_policy.json` `trust_keys` field** — required by KiroCrew's
   governance API to verify the security policy signature on gateway startup.
   This file is mode `0600` but is readable by agent processes running as the
   `kirocrew` user inside the container.

**Threat model:** An agent that reads `admission_policy.json` can extract the
`admiral_secret` and forge Admiral standing orders. This is an accepted risk
for the current single-operator, isolated-container use case — each crew
container runs in its own Podman sandbox and agents are trusted not to be
actively malicious. For multi-operator or untrusted-agent deployments, a
separate policy-signing key (distinct from `admiral_secret`) would close this
gap. See TRN-38 for the investigation that surfaced this.

### Policy signing

The same `admiral_secret` is used to sign the crew's security policy at
injection time. The transport computes HMAC-SHA256 over the canonical
(sorted-keys JSON) policy body and writes the signature into
`~/.kiro/crew/security_policy.json` as `identity.signature`. The gateway
verifies this signature on load; a tampered `security_policy.json` causes a
mismatch and the gateway refuses to continue — an agent cannot forge a valid
policy without the `admiral_secret`.

`admission_policy.json` also carries the `admiral_secret` in its `trust_keys`
field — this is required by KiroCrew's governance API, which reads trust keys
from the policy file at gateway startup. Delivering the secret exclusively via
the `.admiral_secret` file (which would close the agent-readability gap
described in the threat model above) was investigated in TRN-38 but reverted
because `trust_keys` is a hard dependency of the governance API. The
`require_policy_signature: false` flag is set in `admission_policy.json` while
that API contract is being resolved upstream.

### Storage

The `admiral_secret` is stored in plaintext in `crews.json` (the transport
registry at `$TRANSPORT_DATA_DIR/crews.json`, default `/data/crews.json`).

### Threat model

- **Single operator (local):** `DATA_DIR` is only accessible to the user
  running the transport container. The threat model is the same as for
  `GA_API_KEY` — operator-level access to the host is assumed trusted. No
  additional hardening is required.
- **Multi-operator:** If multiple operators share access to the host's data
  volume (or can run `podman inspect ga-transport`), any of them can read
  `admiral_secret` from `crews.json` and forge Admiral standing orders to any
  running crew. For multi-operator deployments, `DATA_DIR` should have `0700`
  permissions and `podman inspect` access should be restricted.
- **Agent-level isolation:** Agent processes inside the crew container cannot
  read `admiral_secret` — it is only accessible via the `.admiral_secret` file
  (mode `0600`, not agent-readable) and is never written to any agent-readable
  policy file.
- **Future hardening:** Encrypting secrets at rest in `crews.json`, or storing
  them separately with tighter file permissions, is tracked in TRN-16.
