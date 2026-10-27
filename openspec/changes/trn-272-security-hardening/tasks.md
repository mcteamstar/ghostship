# Tasks: TRN-272 — Security Hardening

- [ ] H-1: Replace static `_csrf_token` in `dashboard.py` with per-session CSRF token; bind to session on issuance; rotate on new session
- [ ] H-2: Add `GA_TRUSTED_PROXY_CIDR` config key; update `RateLimitMiddleware._caller_key()` to trust XFF only from addresses within the CIDR; default empty (no trusted proxies)
- [ ] H-8: Read `KIRO_FLOW.state` / `CLAUDE_FLOW.state` / `CODEX_FLOW.state` under the flow lock and keep the lock held until `pending["container"]` is safely captured
- [ ] L-1: NFKC-normalise the URL in `_validate_next_url()` before open-redirect validation
- [ ] L-2: Set `Secure` flag on session cookie when the external URL scheme is `https://`
- [ ] L-5: Catch `ValueError` in `GA_BATCH_MAX_TASKS` env parse; raise `ConfigError` with a clear message
- [ ] Run unit tests and e2e suite; confirm all pass
