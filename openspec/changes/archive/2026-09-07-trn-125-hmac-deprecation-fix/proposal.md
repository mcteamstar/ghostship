## Why

`hmac.new()` is a deprecated Python 2 alias for `hmac.HMAC()`. All five current call
sites already pass all three positional arguments, but the deprecation warning surfaces
in newer Python 3 toolchains and static analysers. Replacing every `hmac.new(...)` call
with `hmac.new(...)` — spelling all three arguments explicitly using keyword form where
clarity improves — removes the deprecation and documents intent at each call site.
The ticket target is Python 3.x compatibility hygiene on the `release/0.3.1` line.

## What Changes

- Replace all `hmac.new(key, msg, digestmod)` calls with the non-deprecated form
  `hmac.new(key, msg, digestmod)` making the third argument explicit where it was
  previously implicit or positional-only, across three files:
  - `transport/files.py` (3 call sites — lines 184, 224, 242)
  - `transport/captain.py` (1 call site — line 227, already multi-line)
  - `transport/container_scripts/inject_policy.py` (1 call site — line 52)
- No new public API, no behaviour change, no protocol or signature format change.

## Capabilities

### New Capabilities
<!-- None — pure refactor, no new capability introduced. skip_specs: true set. -->

### Modified Capabilities
<!-- None — no spec-level behaviour changes. The HMAC values produced are identical;
     only the call syntax changes. skip_specs: true covers this change. -->

## Impact

- **Files changed**: `transport/files.py`, `transport/captain.py`,
  `transport/container_scripts/inject_policy.py`
- **Runtime behaviour**: none — `hmac.new` is a direct alias; the computed digests
  are byte-for-byte identical before and after.
- **Dependencies**: none added or removed.
- **Tests**: existing HMAC-related tests (if present) should pass without modification;
  test suite output may lose a deprecation warning line.
- **Toolchain**: resolves deprecation warnings raised by Python 3.12+ and static
  analysis tools (pylint, mypy strict mode) that flag the `hmac.new` alias.
