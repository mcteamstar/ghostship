## Why

KiroCrew 0.4.0 ships four breaking API changes that will prevent ghostship crews from launching or operating correctly if the base image is bumped without code changes. The upgrade also brings a 60% reduction in container startup overhead (1.3s/112MB → 0.5s/54MB) and a new reload-in-place capability that can replace the stop/start cycle ghostship uses for idle recovery.

## What Changes

- **BREAKING** Update crew creation call to include a required `agent` field — 0.4.0 rejects crew creation without one
- **BREAKING** Verify and fix `_copy_agents()` bootstrap timing — the agents config directory is now write-protected at runtime; writes must occur before the gateway starts or switch to `POST /api/agents`
- **BREAKING** Audit `_patch_crew_config()` and `_patch_models()` for settings that now have enforced bounds — previously silent clamping is now a 4xx rejection
- **BREAKING** Grep config-write paths for unexpanded `$VAR` strings — any config field containing a literal shell variable reference is now rejected at the API boundary
- Verify `spawn_min_memory_gb: 0` remains a valid disable sentinel under the new bounds enforcement
- Add `"poolable": false` to any stateful MCP server specs — env-declaring servers are now pooled by default
- Pin Containerfiles to `kirocrew:0.4.0`
- Leverage reload-in-place endpoint to replace stop/start cycles in `_ensure_crew_running` and reconcile logic (optional improvement)

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: Crew creation now requires an `agent` field; `_copy_agents()` bootstrap timing must respect the write-protected agents directory; `_ensure_crew_running` may leverage the new reload-in-place endpoint
- `crew-governance`: Numeric settings in the crew config are now bounds-enforced; unexpanded `$VAR` paths are rejected; MCP server `env` pooling is now on by default

## Impact

- `transport/server.py` — crew creation call, `_copy_agents()`, `_patch_crew_config()`, `_patch_models()`, `_ensure_crew_running`, reconcile logic
- `crews/_base/admission/Containerfile`, `crews/spec-ops/Containerfile` — base image pin bumped to `kirocrew:0.4.0`
- `crews/spec-ops/` MCP configs — poolability audit
- Full regression test pass: launch, dispatch, pickup, nuke
