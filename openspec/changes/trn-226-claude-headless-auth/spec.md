# Delta Spec — TRN-226: Claude headless auth via `claude setup-token`

## New capability: `claude-setup-token-auth`

`POST /login/claude/setup-token` — synchronous headless Claude auth route.

### Request
```
POST /login/claude/setup-token
Authorization: Bearer <GA_API_KEY>
```
No body required.

### Response (success)
```json
{"status": "complete"}
```

### Response (already authenticated)
```
HTTP 409
Already authenticated with Claude. POST /logout/claude first.
```

### Response (OAuth flow in progress)
```
HTTP 409
Claude login already in progress. POST /logout/claude or wait for it to complete.
```

### Response (error)
```json
{"error": "<message>"}
HTTP 500
```

### Behaviour
1. Starts a `ga-claude-login-*` container (same as OAuth path).
2. Runs `claude setup-token` via `container_exec` (not PTY — non-interactive).
3. Polls for `~/.claude/.credentials.json` (or equivalent setup-token output file)
   to be non-empty, up to 60s.
4. Tars `~/.claude/`, writes to `ga-claude-auth` via `_write_claude_auth_file`.
5. Nukes the login container.
6. Returns `{"status": "complete"}`.

The credential is then available to `_inject_claude_auth` at crew launch — no change
to the injection path.

## Modified capability: `claude-auth`

`docs/auth.md` gains a `## Claude headless auth (recommended)` section documenting
`POST /login/claude/setup-token` as the preferred path for server deployments.
The existing OAuth section is kept, retitled `## Claude OAuth login (interactive)`.
The known-limitation note about token expiry is scoped to the OAuth path only.
