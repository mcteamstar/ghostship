# Tasks: TRN-273 — Quality and Correctness Fixes

- [ ] M-3: Validate key names in `yaml_config.py` before `eval`-able emission; add allowlist or switch to safe output format
- [ ] M-6: Make `dispatch()` always return `{"error": ...}` on gateway failure; never return a dict missing `task_id`
- [ ] I-2: Add assertion/guard in `CrewRegistry.batch_*` that detects reentrant use under `with registry:`; document the contract
- [ ] I-3: Narrow `except` clause in `verify_password` to `(ValueError, TypeError)`; let unexpected exceptions propagate
- [ ] I-4: Add `deregister_secret()` to `security.py`; call from nuke cleanup path so `_REGISTERED_SECRETS` doesn't grow indefinitely
- [ ] I-6: Add startup warning when `GA_TRANSPORT_SECRET` is unset and the transport bind address is not loopback
- [ ] L-4: Fix `_validate_model("")` to raise `ValueError` instead of returning `None` silently
- [ ] Run unit tests and e2e suite; confirm all pass
