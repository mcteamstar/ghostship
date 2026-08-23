## Why

`_patch_crew_config` in `transport/server.py` already writes overrides to
`config.local.json` inside each crew at launch time. KiroCrew exposes
`subagent_timeout_secs` (default 1800s — 30 min) and `subagent_max_turns`
(default 100) as configurable fields in `AgentConfig`. The current default is
too conservative for long-running Ghost/Spectre implementation tasks — agents
routinely hit the 30-min wall mid-task, requiring manual recovery dispatches.

Adding these as operator-tunable overrides lets ghostship operators extend the
task timeout without touching KiroCrew internals.

## What Changes

- Add `subagent_timeout_secs` to `_patch_crew_config`, driven by
  `GA_SUBAGENT_TIMEOUT_SECS` env var. Default: 3600 (60 min).
- Add `subagent_max_turns` to `_patch_crew_config`, driven by
  `GA_SUBAGENT_MAX_TURNS` env var. Default: 200.
- Expose both vars in `install.sh` help text and `docs/configuration.md`.
- Both are operator-level (apply to all crews on this transport instance).

## Capabilities

### Modified Capabilities
- `crew-lifecycle`: `_patch_crew_config` gains two new configurable fields written to `config.local.json`

## Impact

- `transport/server.py` — `_patch_crew_config` function (~5 lines)
- `install.sh` — help text addition only
- `docs/configuration.md` — two new env var entries
- `transport/test_transport.py` — update existing `_patch_crew_config` test to assert new fields
