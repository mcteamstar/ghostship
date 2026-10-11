# Delta Spec — TRN-205: `POST /logout` aborts a pending login flow

## Modified capability: `logout`

`POST /logout`, `POST /logout/claude`, `POST /logout/codex` — extended to abort
any in-progress login flow for that backend.

### `POST /logout` (kiro) — updated response

Success, no pending flow:
```json
{"status": "ok", "crews_wiped": [...]}
```

Success, pending flow aborted:
```json
{"status": "ok", "crews_wiped": [...], "aborted_pending_login": true}
```

### `POST /logout/claude` — updated response

Success, no pending flow:
```json
{"status": "ok"}
```

Success, pending flow aborted:
```json
{"status": "ok", "aborted_pending_login": true}
```

### `POST /logout/codex` — same shape as claude.

### Invariant after any `POST /logout*`

- Credential file does not exist
- `_*_login_pending` is `None`
- Login container (if any) is stopped and removed
- A fresh `POST /login*` succeeds without a transport restart
