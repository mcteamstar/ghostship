# TRN-273: Quality and Correctness Fixes

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) identified correctness and
robustness issues in the transport. None are security-critical but all are observable
failure modes.

## What Changes

### M-3: `eval` of yaml_config.py output — key-name injection risk
`bin/lib/yaml_config.py` emits shell `eval`-able output; malformed key names could inject
shell. Fix: validate key names against an allowlist before emission; alternatively, switch
callers to use the Python config loader directly.

### M-6: `dispatch()` returns `task_id=None` silently on gateway protocol error
`transport/tools.py` — gateway connection failure returns a dict without `task_id`
instead of a clear `{"error": ...}`.
Fix: always return an error-keyed dict on failure.

### I-2: `CrewRegistry.batch_*` wrappers can deadlock if called under `with registry:`
Fix: document the no-reentrant contract; add an assertion guard.

### I-3: `verify_password` swallows all exceptions silently
`transport/security.py` — bare `except: return False` masks bugs.
Fix: catch only `(ValueError, TypeError)`; let unexpected exceptions propagate.

### I-4: `_REGISTERED_SECRETS` grows monotonically; log-redaction scan slows over time
`transport/security.py` — the global set never shrinks.
Fix: add a `deregister_secret()` function; call it from `nuke()` cleanup.

### I-6: No startup warning when `GA_TRANSPORT_SECRET` is unset on non-loopback bind
Fix: emit a loud `WARNING` at startup when secret is absent and bind is not loopback.

### L-4: `_validate_model("")` returns `None` silently
Fix: raise `ValueError` or return a sentinel that callers handle explicitly.

## Impact

- `bin/lib/yaml_config.py` — key name validation
- `transport/tools.py` — `dispatch()` error path, `_REGISTERED_SECRETS` deregister on nuke
- `transport/security.py` — `verify_password`, `deregister_secret()`, startup warning
- `transport/registry.py` — batch deadlock guard
