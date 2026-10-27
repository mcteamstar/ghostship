# TRN-273: Quality and Correctness Fixes

## Why

Independent review (indy-0.9.0, review ID 016025f5038b) identified correctness and
robustness issues. All claims verified against source. Some findings were inaccurate and
have been corrected.

Source-verified corrections:
- L-4 (`_validate_model("")` silent None) — intentional by design; empty string is a valid
  "no model" signal equivalent to `None`. No fix needed. Removed from scope.
- I-2 (`CrewRegistry.batch_*` deadlock) — no `batch_*` methods exist in `registry.py`.
  The actual concern is that `RegistryCorruptError` propagates from `_registry_guard`.
  Reframed below.
- I-6 (no startup warning for missing secret) — `server.py:583` already logs a warning.
  Narrowed to: the warning uses `logger.warning` but does not check whether the bind
  is non-loopback; a loopback-only instance silently has no key, which is fine, but a
  non-loopback instance with no key gets only an `INFO`-level log. Tightened below.

## What Changes

### M-3: `yaml_config.py` eval of install.sh output
`bin/install.sh` evals output from `yaml_config.py` (lines 348, 361). The script
already shell-quotes values (line 782 of `yaml_config.py`) but does not validate that
key names contain only safe characters. A key name with shell metacharacters (e.g. from
a malicious/corrupted YAML file) could inject shell commands.
Fix: add key-name validation in `yaml_config.py` output: restrict emitted key names to
`[A-Z0-9_]+`; abort with error on any non-matching key.

### M-6: `dispatch()` returns dict without `task_id` on gateway protocol error
`transport/tools.py` — on gateway connection failure the error path returns
`{"error": ...}` (correct) but the success path always includes `task_id`. Confirmed
the success paths at lines 1905/1914. However, a gateway HTTP error response could fall
through to a path where `task_id` is the raw value from `r.get("id", task_id)` — if
`task_id` was never initialised (headless dispatch), `task_id` could be `None`.
Fix: ensure every dispatch return path either includes a valid `task_id` string or an
`"error"` key; never return `task_id: null`.

### I-3: `verify_password` bare `except Exception` (`transport/security.py:254`)
Confirmed: line 254 has `except Exception: return False`. This swallows unexpected
exceptions (import errors, memory errors, programming bugs) silently.
Fix: narrow to `except (VerifyMismatchError, VerifyInvalidHashError)` from argon2;
let unexpected exceptions propagate so they surface in logs.

### I-4: `_REGISTERED_SECRETS` grows monotonically (`transport/security.py:100`)
Confirmed: the global `set` is added to but never pruned. Secrets from nuked crews
(e.g. `_admiral_secret_hex`) remain registered for the process lifetime; the
redaction scan cost grows with every launch/nuke cycle.
Fix: add `deregister_secret(value: str)` to `security.py`; call it from the nuke
cleanup path.

### I-6: `GA_TRANSPORT_SECRET` warning insufficient on non-loopback bind
`server.py:583` logs at WARNING level when secret is absent, but does not check
whether the bind address is non-loopback. A non-loopback deployment with no secret
is a real exposure; a loopback-only instance is fine without one.
Fix: at startup, if secret is absent AND the bind address is not `127.0.0.1`/`::1`/
`localhost`, elevate to a `CRITICAL`-level log and optionally refuse to start
(configurable via `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND`, default warn-only).

## Impact

- `bin/lib/yaml_config.py` — key name validation on emitted output
- `transport/tools.py` — `dispatch()` `task_id` always set on success path
- `transport/security.py` — `verify_password` exception narrowing, `deregister_secret()`
- `transport/server.py` — startup warning elevation on non-loopback + absent secret
- `transport/config.py` — optional `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND` key
