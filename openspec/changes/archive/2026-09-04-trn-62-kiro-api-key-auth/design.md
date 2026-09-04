## Context

See proposal.md. The key question from the original TRN-62 investigation is whether kiro-cli supports an API key env var that bypasses device auth for ACP sessions (not just `kiro-cli chat`). Based on kiro-cli's support for `KIRO_API_KEY` as an env var accepted by the Gateway spawner, this is confirmed viable — the env var is forwarded to kiro-cli subprocesses spawned by the Gateway.

## The Two Auth Paths

### Path A: Device-code (existing, default)

```
install.sh → ga-transport → POST /login → browser → GET /login → ga-kiro-auth
launch → _finish_crew_setup → _inject_auth → crew SQLite
```

Unchanged. When `KIRO_API_KEY` is unset, this path is used.

### Path B: API key (new)

```
ghostship.conf: KIRO_API_KEY=<key>
install.sh → ga-transport env: KIRO_API_KEY=<key>
launch → podman create --env KIRO_API_KEY=<key> → crew container
```

No login flow. No `ga-kiro-auth`. No `inject_auth.py`. kiro-cli inside the crew reads `KIRO_API_KEY` from its environment and authenticates directly.

## Implementation

### 1. `transport/config.py`

Add `kiro_api_key: str = ""` to `Config` and `kiro_api_key=os.environ.get("KIRO_API_KEY", "")` to `from_env()`.

### 2. `transport/server.py`

Export `KIRO_API_KEY = cfg.kiro_api_key` at module level (alongside `KIRO_LICENSE`).

In `launch()`, the auth guard that calls `_initiate_login()` currently runs unconditionally when `ga-kiro-auth` is absent. Wrap it:

```python
if not KIRO_API_KEY:
    # existing device-code guard
    if not auth_b64:
        return _initiate_login(...)
```

When `KIRO_API_KEY` is set, skip the guard entirely — no login required.

### 3. `transport/lifecycle.py` — `_finish_crew_setup`

The env vars passed to `podman create` for crew containers include `KIRO_LICENSE`. Add `KIRO_API_KEY` to the same list, conditionally:

```python
env_vars = {
    "KIRO_LICENSE": KIRO_LICENSE,
    **({"KIRO_API_KEY": KIRO_API_KEY} if KIRO_API_KEY else {}),
}
```

Also skip `_inject_auth` when `KIRO_API_KEY` is set:

```python
if not KIRO_API_KEY:
    _inject_auth(podman, container, auth_b64)
```

### 4. `scripts/install.sh`

Add `KIRO_API_KEY` to the `ga-transport` service env block in `compose.yml` generation (alongside `KIRO_LICENSE`):

```yaml
KIRO_API_KEY: "${KIRO_API_KEY:-}"
```

### 5. `config/ghostship.conf.example`

Add a commented section:

```bash
# ── kiro-cli auth ─────────────────────────────────────────────────────────────
# Option A — API key (Pro+, headless): set KIRO_API_KEY to skip the device flow.
# KIRO_API_KEY="<your-api-key>"

# Option B — Device code (default, all tiers): leave KIRO_API_KEY unset.
# Run POST /login after install to complete the browser-based auth flow.
# For IAM Identity Center (org-licensed), also set:
# KIRO_IDENTITY_PROVIDER="https://d-xxxxxxxxxx.awsapps.com/start/#/"
# KIRO_REGION="us-east-1"
# KIRO_LICENSE="pro"
```

### 6. `docs/auth.md`

Add a "Headless / API key auth" section before the existing "First login" section, explaining the two paths and when to use each.

## No migration concerns

Existing installs without `KIRO_API_KEY` are unaffected. The env var defaults to empty, the guard remains in place, and the device-code path is unchanged. Re-running `install.sh` after adding `KIRO_API_KEY` to `ghostship.conf` rebuilds `compose.yml` with the new env var — the transport restarts and picks it up.
