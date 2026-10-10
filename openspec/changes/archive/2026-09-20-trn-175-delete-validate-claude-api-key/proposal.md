## Why

`_validate_claude_api_key` in `transport/config.py` is an empty-body function that exists only to be called by `Config.validate()`, which is itself documented as a no-op. Additionally, the `server.py` startup comment claims `validate()` "Raises ConfigError if GA_CREW_ACP_BACKEND=claude and GA_CREW_ANTHROPIC_API_KEY is unset" — a statement that has been false since TRN-170 superseded startup validation with lazy credential checking. An operator reading this comment gets a dangerously incorrect expectation about what validation is enforced at startup.

## What Changes

- Delete `_validate_claude_api_key` from `transport/config.py` (L85–97) — empty-body function, never does anything
- Replace `Config.validate()` body with `pass` and update its docstring to accurately state: "No-op. Retained for API compatibility. Credential validation is lazy — deferred to `launch()` time."
- Fix the stale comment at `transport/server.py` ~L4187: replace "Raises ConfigError if GA_CREW_ACP_BACKEND=claude and GA_CREW_ANTHROPIC_API_KEY is unset" with "No-op — credential validation is lazy (deferred to launch())"

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

_(none — no externally observable behaviour changes; validate() was already a no-op)_

## Impact

- `transport/config.py` — ~13 lines deleted, `validate()` body replaced with `pass`
- `transport/server.py` — 1 comment line updated
- No test changes needed — existing tests already assert `validate()` does not raise and will continue to pass
- No API changes, no config changes
