# Auth & Security

## Managing credentials: `ghostship auth`

Manage backend credentials with the CLI:

```bash
ghostship auth login <backend>                    # store a credential (kiro|claude|codex)
ghostship auth login <backend> --profile <name>   # store under a named profile
ghostship auth logout <backend>                   # clear the default profile's credential
ghostship auth logout <backend> --profile <name>  # clear a specific named profile
ghostship auth status                             # show all profiles for every backend
```

Credentials live in `DATA_DIR/credentials/<backend>/<profile>.json` and are resolved per crew launch — not in the config file. Successful `launch` responses include `acp_profile`, the resolved profile recorded for the crew.

### Credential lifecycle

| Backend | Login-flow methods propagated to matching running crews | Static methods injected at container creation |
|:--------|:--------------------------------------------------------|:----------------------------------------------|
| Kiro | `builder-id`, `identity-center` | `api-key` |
| Claude | `oauth` | `api-key`, `setup-token` |
| Codex | `chatgpt` | `api-key` |

When a login-flow method completes, Ghostship attempts to inject the newly stored credential into crews registered as running for the same backend and profile. Stopped crews are not targeted; their stored flow credential is injected when they next wake. A flow-completion response can include `propagation_failed` crew IDs if an injection fails; retry one crew with [Refresh a crew's auth](#refresh-a-crews-auth). Switching a profile from a static method to a login-flow method does not remove the static environment value already present in a crew, so recreate that crew to complete the method change.

Static credentials are injected into the container environment at creation and are not propagated. After rotating a static value or changing its method, an already-running container keeps its launch-time environment value. When the crew stops, the launcher refuses to wake it if the stored credential is missing or no longer matches the container's static method/value. Because `evac` follows the same wake path, preserve the workspace with `evac` before changing or removing the static credential whenever possible. If the crew is already stopped after the credential changed or was removed, restore the exact launch-time static method and value under its recorded profile (for example, with `ghostship auth login <backend> --profile <name> --method <method> --yes`), then wake it and run `evac`. Without that credential, `evac` cannot wake the crew. Do not `nuke` until `evac` succeeds: `nuke` deletes the workspace and home volumes. Then `launch` a replacement and `supply` the saved workspace. See [Repository transfer](architecture.md#repository-transfer).

- On a terminal, `login` presents a numbered method menu per backend; in non-interactive use, pass `--method`.
- Secrets are read from a hidden terminal prompt or stdin — never appear in `argv` or output.
- The transport URL and bearer key are **discovered automatically** from the installed containers (Podman inspect). Override with `--url` / `--api-key`, or `GHOSTSHIP_URL` / `GHOSTSHIP_API_KEY` env vars.
- `ghostship auth logout <backend>` cancels any pending login and clears the selected profile credential. It does not remove credentials already injected into running containers. A stopped crew cannot wake while its profile credential is absent.

Per-backend methods:

| Backend | Methods (`--method`) |
|:--------|:---------------------|
| kiro    | `builder-id`, `identity-center`, `api-key` |
| claude  | `oauth` (Pro/Max), `api-key`, `setup-token` |
| codex   | `chatgpt` (ChatGPT sign-in), `api-key` |

> **Credential profiles:** each backend supports multiple named credential profiles (e.g. `default`, `corp`). When `--profile` is omitted, the `default` profile is used. The name `default` is reserved — it is written internally by the implicit fallback and migration path and cannot be specified explicitly. Non-secret backend base URLs (`backends.<b>.base_url`) can be set in `config/ghostship.yaml`.

### Named profiles

Multiple credentials can coexist under one backend, useful for different AWS accounts, billing contexts, or org identities:

```bash
# Store a personal kiro credential (default profile)
ghostship auth login kiro

# Store a corporate kiro credential under a named profile
ghostship auth login kiro --profile corp

# Launch a crew using the corp profile
ghostship auth status   # shows all profiles; use the MCP launch tool with profile="corp"

# Remove just the corp profile
ghostship auth logout kiro --profile corp
```

Profile resolution at `launch` time:
1. If `profile` is explicitly specified → use it.
2. If only one profile exists for the backend → use it implicitly.
3. Otherwise → use `default`.

### Launch when a credential is missing

The `launch` MCP tool checks credentials before it registers or creates a crew. If the resolved profile is `default` and has no stored credential, `launch` starts that backend's login flow and returns `not_authenticated` with the login URL/code, or reports that a login is already pending. Complete the returned flow as directed, then retry `launch`. This response does not create a crew, so there is nothing to nuke.

If the resolved profile is named and has no stored credential, `launch` returns `not_authenticated` without starting a flow or falling back to another profile. Authenticate it first with `ghostship auth login <backend> --profile <name>`, then retry `launch`. In non-interactive use, also pass `--method <method>`.

### Refresh a crew's auth

A running crew keeps the credential it was launched with, plus any login-flow credential pushed to it since. A refresh re-applies the credential **currently stored** for one crew's backend and profile. Use it to retry a crew that a login completion listed in `propagation_failed`, or to check whether a static credential change needs the crew recreated.

- A refresh only re-applies what is stored. It does not contact the provider or extend a session. If the stored login has expired, log in again first (`ghostship auth logout <backend>`, then `ghostship auth login <backend>`).
- It takes no credential and always uses the backend and profile recorded for the crew. It never starts, stops or recreates a crew.
- For a Kiro crew, a successful refresh also clears the crew's recorded sign-in state so the next dispatch re-checks it.

Trigger it from [Radar](radar.md#refresh-a-crews-auth), with the **Refresh auth** button in the crew's detail panel, or call the transport's REST API:

- **`POST /crews/{crew_id}/auth/refresh`** — operator endpoint. Requires `Authorization: Bearer <key>` when `GA_API_KEY` is set. It answers 403 to any request that carries a browser `Origin` header, and 405 to other methods. It is not an MCP tool.
- **`POST /internal/crews/{crew_id}/auth/refresh`** — portside-internal twin used by Radar. Requires `X-Transport-Token` and no bearer key. It runs the same operation and returns the same body.
- The request has no body and takes no credential. Every defined outcome is HTTP 200 with the outcome in `status`, so branch on `status`. An unknown crew is 404, missing or wrong credentials are 401, and an unexpected transport error is 500 with `{"error": "crew auth refresh failed"}`.

> **Reaching the operator endpoint.** The transport publishes no host port, and the Portal configuration generated by this release forwards `/crews/*/dashboard` to it but has no route for `/crews/*/auth/refresh`. Until the Portal routes that path, the operator endpoint is reachable only by a caller that is already on `ga-portside` and can present both the transport token and the bearer key. Radar's button uses the internal route and needs no Portal route.

Against a transport API you can reach directly:

```bash
curl -sS -X POST -H "Authorization: Bearer $GHOSTSHIP_API_KEY" \
  "$TRANSPORT_URL/crews/my-crew/auth/refresh" | jq
```

```json
{
  "status": "refreshed",
  "crew_id": "my-crew",
  "backend": "kiro",
  "profile": "default",
  "message": "The current stored credential was injected into the running crew."
}
```

| `status` | Meaning | What to do |
|:---------|:--------|:-----------|
| `refreshed` | The stored login-flow credential was injected into the running crew. | Nothing. |
| `pending_on_wake` | The crew is stopped. It receives the stored login-flow credential the next time it wakes. | Nothing, or wake it. |
| `current` | Static credential: the container already holds the stored value. | Nothing. |
| `recreate_required` | The stored static credential or its method differs from the container's launch-time environment, which cannot change in place. | Recreate the crew with its workspace preserved (below). |
| `credential_missing` | Nothing is stored for the crew's backend and profile. | `ghostship auth login <backend>` (add `--profile <name>` for a named profile), then refresh again. |
| `refresh_failed` | The comparison or the injection failed. The crew was left as it was. | Check the transport log, then retry. |

Login-flow methods (`builder-id`, `identity-center`, `oauth`, `chatgpt`) are written into the crew's home: a completed login pushes the credential to matching running crews, and a stopped crew receives it when it wakes. A refresh covers the gap when a push failed. Static methods (`api-key`, `setup-token`) are environment values fixed at container creation, so a refresh can only compare them. A profile switched from a static method to a login flow also reports `recreate_required`, because the old value stays in the container's environment.

**Recovering from `recreate_required`.** Preserve the workspace, then replace the crew. This is the workflow described under [Credential lifecycle](#credential-lifecycle):

1. Save the workspace with `evac`. A running crew still works with its launch-time value, so `evac` succeeds now. A stopped crew cannot wake while the stored credential differs from its container: restore the launch-time method and value under its profile (`ghostship auth login <backend> --profile <name> --method <method> --yes`), wake it, then `evac`.
2. Only after `evac` succeeds, `nuke` the crew. `nuke` deletes its workspace and home volumes.
3. `launch` a replacement with the same profile and `supply` the saved workspace. See [Repository transfer](architecture.md#repository-transfer).

### Session lifetime (estimates)

Login-flow sessions end after a while. These are rough observations, not guarantees:

| Method | Observed session lifetime |
|:-------|:--------------------------|
| Codex `chatgpt` | about 10 days |
| Kiro `identity-center` | about 90 days |

Actual lifetimes depend on the provider and on the account or organisation's settings, and they can change. Treat them as a prompt to re-check, not an expiry date. No estimate is recorded for the other methods.

When a session ends, log in again (`ghostship auth logout <backend>`, then `ghostship auth login <backend>`). Completion updates matching running crews and stopped crews pick it up on wake. If a crew still fails after that, refresh it as above.

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

The Identity Center start URL **must include `/#/`**. Omit `--method` for the terminal method menu, or pass it explicitly in non-interactive use. See [Launch when a credential is missing](#launch-when-a-credential-is-missing) for how `launch` handles unauthenticated profiles.

### Identity provider config

Identity Center defaults live in `config/ghostship.yaml`:

```yaml
backends:
  kiro:
    identity_center:
      url: "https://identitycenter.amazonaws.com/ssoins-abc123"
      region: "us-east-1"
```

Set defaults in `config/ghostship.yaml` under `backends.kiro.identity_center` — see [configuration.md#config-file](configuration.md#config-file).

### Secret rotation

For expired `builder-id` or `identity-center` auth, run `ghostship auth logout kiro` then `ghostship auth login kiro`; completion updates running Kiro crews assigned to that profile. `api-key` rotation follows the static credential rules above.

### Uninstall retention

`ghostship uninstall` keeps `DATA_DIR/credentials/` so a later install can reuse logins. Pass `--purge-auth` to remove them.

### Auth API

HTTP endpoints on the MCP port — driven by the CLI, not MCP tools. Require `Authorization: Bearer <key>` when `GA_API_KEY` is set.

```
UNAUTHENTICATED  ──[POST /login/kiro/builder-id]──►  PENDING  ──[GET /login/kiro → complete]──►  AUTHENTICATED
                ◄──────────────────────────────────────[POST /logout/kiro]────────────────────────────────────────┘
```

- **`POST /login/kiro/builder-id`** / **`POST /login/kiro/identity-center`** — starts the flow, returns `login_url` and `code`. Optional `profile` field in JSON body (default: `"default"`).
- **`POST /login/kiro/api-key`** — stores a pasted API key. Optional `profile` field in JSON body.
- **`GET /login/kiro`** — polls completion. Optional `?profile=<name>` query param. On success writes auth and returns `complete`.
- **`GET /login/kiro/profiles`** — returns `{"profiles": [...]}`, sorted list of stored profile names.
- **`POST /logout/kiro`** — cancels any pending flow, removes the credential. Optional `?profile=<name>` query param (default: `"default"`). Idempotent. Running crews unaffected.

---

## Claude auth

### Methods

| Method | For |
|:-------|:----|
| `setup-token` | Unattended/server deployments. Long-lived token from `claude setup-token`. **Recommended.** |
| `api-key` | Anthropic pay-per-token API key. |
| `oauth` | Claude Pro/Max subscription, interactive authorisation-code flow. |

### Prerequisites

Enable the Claude backend by adding a `claude: {}` section under `backends:` in `config/ghostship.yaml`, then run `ghostship install`. See [configuration.md](configuration.md).

### Setup-token (headless, recommended) {#setup-token-headless-recommended}

1. On your own machine: `claude setup-token`, approve in browser, copy the token.
2. `ghostship auth login claude --method setup-token` and paste the token.

The token is long-lived but does expire. When crews fail Claude auth, run `claude setup-token` again and `ghostship auth login claude --method setup-token`. This is a static credential: existing containers keep the value injected at creation, and a stopped crew cannot wake after the stored value changes. Recreate the crew to use the replacement token; preserve its workspace as described above.

### OAuth (interactive)

```bash
ghostship auth login claude --method oauth
```

The CLI starts a flow, prints the URL, and polls for completion. After approval the browser shows `<code>#<state>` — the CLI submits it automatically. If no code is submitted within 15 minutes, or the exchange doesn't complete within 120 seconds, the flow expires.

OAuth tokens may expire over time. Re-authenticate with `ghostship auth logout claude` then `ghostship auth login claude`. Completing the flow updates matching running crews; stopped crews receive the stored OAuth credential when they next wake.

### Auth API

```
UNAUTHENTICATED  ──[POST /login/claude/oauth]──►  PENDING  ──[POST /login/claude/oauth/code]──►  CODE SUBMITTED  ──[GET /login/claude → complete]──►  AUTHENTICATED
               ◄──────────────────────────────────────────────────[POST /logout/claude]──────────────────────────────────────────────────────────────────────────────┘
```

- **`POST /login/claude/oauth`** — starts the OAuth flow. Returns `{"login_url": "..."}`. Returns 409 if a flow is already in progress. Optional `profile` field in JSON body.
- **`POST /login/claude/oauth/code`** — body `{"code": "<code>#<state>"}`. Returns 202. The code is never logged.
- **`POST /login/claude/api-key`** — stores a pasted Anthropic API key. Optional `profile` field in JSON body.
- **`POST /login/claude/setup-token`** — stores a pasted claude setup-token. Optional `profile` field in JSON body.
- **`GET /login/claude`** — polls completion. Optional `?profile=<name>` query param. Returns `complete` / `pending` / `410 expired`.
- **`GET /login/claude/profiles`** — returns `{"profiles": [...]}`, sorted list of stored profile names.
- **`POST /logout/claude`** — cancels pending flow, removes credential. Optional `?profile=<name>` query param (default: `"default"`). Idempotent. Running crews unaffected.

---

## Codex auth

### Prerequisites

Enable the Codex backend by adding a `codex: {}` section under `backends:` in `config/ghostship.yaml`, then run `ghostship install`. See [configuration.md](configuration.md).

### Authenticate

```bash
ghostship auth login codex   # presents method menu: chatgpt or api-key
```

For `chatgpt`: the CLI starts a flow, prints the URL, and polls for completion. Approve in your browser. Completing the flow updates matching running Codex crews; stopped crews receive the stored OAuth credential when they next wake. Codex `api-key` rotation follows the static credential rules above.

### Auth API

```
UNAUTHENTICATED  ──[POST /login/codex]──►  PENDING  ──[GET /login/codex → complete]──►  AUTHENTICATED
              ◄──────────────────────────────────────[POST /logout/codex]───────────────────────────────┘
```

- **`POST /login/codex`** — starts the OAuth flow. Returns `{"status": "pending", "login_url": "..."}`. Optional `profile` field in JSON body.
- **`GET /login/codex`** — polls completion. Optional `?profile=<name>` query param. Returns `complete` / `pending`.
- **`GET /login/codex/profiles`** — returns `{"profiles": [...]}`, sorted list of stored profile names.
- **`POST /logout/codex`** — cancels pending flow, removes credential. Optional `?profile=<name>` query param (default: `"default"`). Idempotent. Running crews unaffected.

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

## Admiral mail signing {#admiral-mail-signing}

### Ed25519 keypair

At crew launch the transport generates an **Ed25519 keypair**. The private seed stays host-side and never enters the container. The public key is delivered as a read-only, root-owned Podman secret at `/run/secrets/.admiral_public_key`.

Every standing order written to `/var/mail/captain` carries an `X-Admiral-Sig:` header. Raven calls `verify-admiral-sig` to confirm authenticity before acting.

**Storage:** `crews.json` stores only a non-reversible `sha256:<hex[:16]>` fingerprint per secret. The Admiral Ed25519 private seed is persisted to `DATA_DIR/secrets/<crew_id>` (mode `0600`).

### HMAC-SHA256 policy signing

A separate `policy_signing_key` signs `security_policy.json` via HMAC-SHA256. A tampered policy causes a mismatch and the gateway refuses to start.

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

Dashboard ports are session-gated at Portal (Caddy) and again at Transport's crew UI proxy. This second check also blocks direct internal callers that have the transport secret but no valid `gs_session`. See [portal.md](portal.md) for setup. `gs_session` cookies have a configurable TTL (`GA_PORTAL_SESSION_TTL_SECS`, default 24 h) and are in-memory — they reset on transport restart.
