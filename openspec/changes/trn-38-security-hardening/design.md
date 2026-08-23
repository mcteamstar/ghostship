## Context

See proposal.md — Why. Nine specific issues identified by Banshee, all in `transport/server.py` plus the crew bootstrap path. Key current-state facts:

- `HOST` default is `0.0.0.0` (line 84). No API key is required by default, so the transport is open to any LAN client.
- `_sign_file_url` and `_sign_upload_url` both call `.hexdigest()[:16]` — 64-bit truncation (lines 4382, 4827).
- `_sign_upload_url` comment explicitly states that mode (`unpack`/`bundle`) is *outside* the signed payload (line 4823-4825). `_verify_file_token` (called from `_handle_file_put`, line 4779) never receives the mode.
- `_handle_file_get` and `_handle_file_put` extract `crew_id` from path params and use it directly in `_require_crew`/`_ensure_crew_running` without format validation (lines 4646-4647, 4765-4766).
- `evac()` (line 2953) does `clean = path.lstrip("/")` with no guard against empty `path`, so `evac(path="", crew_id=...)` signs a URL for the workspace root.
- `_save_registry` (line 877) writes via `tmp.write_text()` then `os.replace()` — no chmod.
- `admiral_secret` is generated at launch, stored in the in-process registry dict (line 2850) AND read back out to verify Admiral messages (line 1125). The crew container receives it via `_inject_policy` which bakes it into `admission_policy.json` inside the crew (line 2735).
- `dangerously_skip_permissions=True` appears at line 2667 with no explanatory comment.

## Goals / Non-Goals

**Goals:**
- Eliminate each of the nine findings with the minimum targeted change.
- Preserve the existing external API surface — no tool signature changes, no URL format breaks (token format change is internal).
- Maintain backward-compatibility for the `admiral_secret` migration: crews launched before this change still work.

**Non-Goals:**
- Rotating or expiring the `_FILE_SECRET` (no key-rotation mechanism today).
- Adding API-key auth where none is configured (scope of Finding 4 is only the default bind; GA_API_KEY already handles auth when set).
- Converting any other env vars or secrets to Podman secrets (only `admiral_secret` has a within-container exposure problem here).
- Eliminating `dangerously_skip_permissions` entirely — only annotating it.

## Decisions

### D1: Extend HMAC from `[:16]` to `[:32]`

**Choice:** Replace both `[:16]` slices in `_sign_file_url` and `_sign_upload_url` with `[:32]`, and update the matching `[:16]` in `_verify_file_token`'s `expected` comparison. `hmac.compare_digest` continues to work since lengths match.

**Rationale:** `[:32]` gives 128-bit security (2^128 brute-force) while remaining a hex substring of the full SHA-256 digest. Using the full digest (64 chars) is also acceptable but `[:32]` matches TRN-27's precedent for similar token changes and keeps URL query strings shorter.

**Alternative considered:** Use full hex digest (64 chars). Adds no meaningful security over 128 bits for HMAC-SHA256 token forgery; rejected for URL length.

### D2: Include mode in upload token payload

**Choice:** Change `_sign_upload_url` signature to `_sign_upload_url(crew_id, path, unpack=False, bundle=False)`. Encode mode as a single field: `"unpack"`, `"bundle"`, or `""`. Update the payload string:
```
payload = f"{crew_id}:{path}::{mode}:{expires}"
```
Update `_verify_file_token` to accept an optional `mode` parameter and include it identically in its payload reconstruction. `_handle_file_put` must extract `unpack`/`bundle` from query params *before* calling `_verify_file_token` and pass the derived mode.

**Rationale:** The comment in the existing code (lines 4823-4825) argued that mode was safe to exclude because "both modes only write caller-supplied bytes to a path the caller was already authorized to write." Banshee correctly flags this: a `bundle=True` request clones a git repo from attacker-controlled bytes, which has substantially different semantics and risk from a plain file write. Signing the mode closes the replay.

**Alternative considered:** Keep mode out of signature but validate mode consistency in business logic (allow any mode on any token). Rejected — the point of the signed payload is to bind the token to all security-relevant parameters.

**Note on `supply()` MCP tool:** `supply()` must pass `unpack`/`bundle` to `_sign_upload_url`. The returned URL already appends `&unpack=1` / `&bundle=1` as query params; those now become part of the signed scope as well as the URL.

### D3: Change HOST default to 127.0.0.1

**Choice:** Change line 84 from `os.environ.get("HOST", "0.0.0.0")` to `os.environ.get("HOST", "127.0.0.1")`.

**Rationale:** The spec says `HOST` defaults to `0.0.0.0` "inside the container, published to `127.0.0.1` only by `install.sh`". This is a defence-in-depth gap: if the container ever runs without `install.sh`'s `--publish 127.0.0.1:...` flag (e.g., direct `podman run` during development), the transport is open on the LAN. Changing the default to loopback makes the secure path the default; operators who need LAN exposure set `HOST=0.0.0.0` explicitly.

**Alternative considered:** Keep `0.0.0.0` but document more clearly. Rejected — documentation doesn't protect a developer's unguarded test instance.

### D4: crew_id regex validation in file handlers

**Choice:** Add a module-level `CREW_ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$|^[a-z0-9]$')` (the same pattern already used at line 2569 in `launch()`). Call it at the top of `_handle_file_get` and `_handle_file_put`, returning 400 if it doesn't match.

**Rationale:** Without this guard, a crafted request can supply a `crew_id` containing path separators or shell metacharacters and attempt to influence path construction. The HMAC check catches *replay* attacks but doesn't prevent *new* crafted requests against weak secrets.

**Alternative considered:** Extract the regex from `launch()` into a shared validator function. Acceptable; implementation can do either — module-level constant with inline `re.fullmatch` is simpler and avoids a new abstraction.

### D5: Reject empty path in evac

**Choice:** Add a guard in `evac()` immediately after `clean = path.lstrip("/")`:
```python
if not clean:
    return {"error": "path must not be empty"}
```

**Rationale:** An empty path resolves to the workspace root. Signing a URL for the workspace root and serving it would stream the entire workspace as a tar (or attempt to diff `/`). This is a straightforward validation gap.

### D6: Admiral secret via environment variable

**Choice:** Generate `admiral_secret` at launch as before. Instead of (or in addition to) baking it into `admission_policy.json`, inject it into the crew container as an environment variable `KIRO_ADMIRAL_SECRET` using `podman container exec` or `podman run -e`. The policy-injection function `_inject_policy` removes the `admiral_secret` field from the `admission_policy.json` content it writes. The gateway inside the crew reads `KIRO_ADMIRAL_SECRET` from its environment; the transport's `verify-admiral-sig` helper is updated accordingly.

**Approach for backward compat:** The `admission_policy.json` template already seeds the file; existing crews that still have the field in their policy will continue to work until `nuke`'d and relaunched. New crews get the env-var delivery only.

**Rationale:** `admission_policy.json` is world-readable by any agent process inside the crew container (it must be readable by the gateway). Delivering the secret via the container's env avoids it being file-accessible to agents that can run `cat` but not inspect container metadata.

**Alternative A considered:** Restrict `admission_policy.json` to gateway-UID-only (`0400`, owned by gateway process user). Rejected for this change — the transport doesn't set a dedicated gateway UID, and enforcing file ownership at `container_exec` time is fragile. The env-var path is cleaner.

**Alternative B considered:** Podman secret (same path as TRN-27's `GA_API_KEY`). Requires secret creation at launch time with `podman secret create`. Adds complexity; env var injection via `podman run -e` is sufficient and already used for other crew config.

### D7: chmod 0o600 on crews.json

**Choice:** Add `os.chmod(REGISTRY_PATH, 0o600)` after `os.replace(tmp, REGISTRY_PATH)` in `_save_registry`.

**Rationale:** `os.replace` preserves the permissions of the target file if it already exists; the first write takes the process umask. An explicit chmod after every write is the safest guarantee.

### D8: Annotate dangerously_skip_permissions

**Choice:** Add an inline comment at line 2667 explaining why the bypass is needed (the crew gateway process runs as a different UID than the transport, so normal permission enforcement would prevent the operation) and noting that the flag bypasses normal access control for that specific operation.

## Risks / Trade-offs

- **[Risk] Token format break** — Existing in-flight presigned URLs (signed with 16-char HMAC or unsigned mode) will be rejected after the update. TTL is GA_FILE_TTL_SECS (default 5 min), so exposure window is short. → Mitigation: Deploy update; any in-flight supply/evac URLs expire naturally within 5 min. Document in migration plan.
- **[Risk] admiral_secret migration for existing crews** — Crews launched before this change have the secret in `admission_policy.json`. The gateway must support reading from both env and file to avoid breaking them. → Mitigation: Gateway reads `KIRO_ADMIRAL_SECRET` env first; falls back to `admission_policy.json` field with a deprecation log. New launches omit the field.
- **[Risk] HOST change breaks existing docker-compose/podman-run setups that relied on 0.0.0.0 default** — Users who run the transport directly without `HOST=0.0.0.0` will find it stops being reachable from other hosts. → Mitigation: Document the change prominently. `install.sh` already sets the published port correctly, so install.sh-managed setups are unaffected.
- **[Trade-off] `_sign_upload_url` signature change** — All callers of `_sign_upload_url` must be updated to pass mode. There is currently one call site (`supply()`). Straightforward.

## Migration Plan

1. Deploy updated `transport/server.py`. All new presigned URLs use 128-bit HMAC and include mode in upload tokens.
2. Any in-flight 64-bit URLs from before the deploy expire within GA_FILE_TTL_SECS (default 5 min) and are rejected with 403 — no data loss, callers simply re-request.
3. Existing crew containers continue to have `admiral_secret` in `admission_policy.json`; they continue to work via the fallback read path.
4. New crews launched after deploy receive `KIRO_ADMIRAL_SECRET` via env and do not have the field in their policy file.
5. `crews.json` permissions are corrected on the next registry write (happens frequently: any tool call that touches a crew).
6. HOST change is effective immediately on process restart; operators on non-install.sh setups must set `HOST=0.0.0.0` to restore prior LAN exposure.

## Open Questions

- Does the `verify-admiral-sig` script inside the crew image need to be rebuilt to read from env, or does the gateway itself mediate all Admiral verification? (Affects whether a crew image rebuild is required for D6 or just a transport-side + config change.) This should be confirmed before implementing D6 — if the crew image needs patching, the task breakdown needs a crew image build step.
