# Tasks: TRN-272 — Security Hardening

- [ ] H-1: Replace static `_csrf_token` in `dashboard.py` with per-session token; bind to session on issuance
- [ ] H-2: Add `GA_TRUSTED_PROXY_CIDR` config key; make `RateLimitMiddleware._caller_key()` use ASGI IP unless request comes from trusted proxy
- [ ] H-8: Hold flow lock across state-read and `pending["container"]` dereference in Kiro, Claude, and Codex login handlers
- [ ] H-9: Add `@_registry_guard` decorator to `nuke()` in `transport/tools.py`
- [ ] L-1: Normalise URL (NFKC) before open-redirect validation in `_validate_next_url()`
- [ ] L-2: Set `Secure` flag on session cookie when external URL is `https://`
- [ ] L-5: Catch `ValueError` in `GA_BATCH_MAX_TASKS` env parse; raise `ConfigError`
- [ ] Run unit tests and e2e suite; confirm all pass
