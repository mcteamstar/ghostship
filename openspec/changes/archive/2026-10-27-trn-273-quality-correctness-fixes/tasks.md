# Tasks: TRN-273 — Quality and Correctness Fixes

- [x] M-3: Add key-name validation in `yaml_config.py` — restrict emitted keys to `[A-Z0-9_]+`; abort with error on any non-matching key name before shell eval
- [x] M-6: Audit `dispatch()` and `batch_dispatch()` return paths — ensure every success path returns a non-None `task_id`; every failure path returns `{"error": ...}`
- [x] I-3: Narrow bare `except Exception` in `verify_password` (`security.py:254`) to argon2-specific exceptions; let unexpected exceptions propagate
- [x] I-4: Add `deregister_secret(value: str)` to `security.py`; call from nuke cleanup path to prune `_REGISTERED_SECRETS`
- [x] I-6: In `server.py` startup, if `GA_TRANSPORT_SECRET` is absent and bind address is non-loopback, log at `CRITICAL` level (not just `WARNING`)
- [x] Run unit tests and e2e suite; confirm all pass
