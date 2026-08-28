## 1. Pre-implementation verification (unblocks all other groups)

- [ ] 1.1 Confirm agent template name for `POST /api/chat/slots` from KiroCrew 0.4.0 changelog or source (OQ-1)
- [ ] 1.2 Confirm reload-in-place endpoint path and request shape from 0.4.0 release notes (OQ-2)
- [ ] 1.3 Confirm `spawn_min_memory_gb: 0` is still accepted in 0.4.0; if floored, identify the `admission_gate: false` equivalent (OQ-3)
- [ ] 1.4 Pull `ghcr.io/kirodotdev/kirocrew:0.4.0` locally and verify it is available before building crew images

## 2. Pin Containerfiles to KiroCrew 0.4.0

- [ ] 2.1 Update `crews/_base/admission/Containerfile`: change `FROM ghcr.io/kirodotdev/kirocrew:0.3.0` to `FROM ghcr.io/kirodotdev/kirocrew:0.4.0`
- [ ] 2.2 Update `crews/spec-ops/Containerfile` if it has a separate base image pin
- [ ] 2.3 Build both images locally and confirm they build clean

## 3. Add `agent` field to crew creation (D1, requires 1.1)

- [ ] 3.1 Locate the `POST /api/chat/slots` call in `transport/server.py` (likely in `_finish_crew_setup` or nearby)
- [ ] 3.2 Add `"agent": "<template-name>"` to the request payload using the value confirmed in 1.1
- [ ] 3.3 Add a clear error message if the creation call returns 4xx, surfacing the agent-template-not-found case

## 4. Verify `_copy_agents()` timing (D2)

- [ ] 4.1 Trace the bootstrap sequence in `_finish_crew_setup` and confirm `_copy_agents()` is called before the first `_wait_gateway` call
- [ ] 4.2 If `_copy_agents()` runs after gateway start, move it earlier in the sequence or switch to `POST /api/agents`
- [ ] 4.3 Add a log line confirming when agent copy completes relative to gateway start

## 5. Audit numeric config bounds (D3, requires 1.3)

- [ ] 5.1 List every field written by `_patch_crew_config()` and `_patch_models()` with its current value
- [ ] 5.2 Cross-reference each field against the 0.4.0 bounds table
- [ ] 5.3 For any out-of-range value, clamp at the ghostship layer before the API call and log a warning
- [ ] 5.4 Verify `spawn_min_memory_gb: 0` handling per OQ-3 resolution; update if needed

## 6. Fix unexpanded $VAR in config writes (D4)

- [ ] 6.1 Grep `_patch_crew_config`, `_patch_models`, and any other config-write functions in `transport/server.py` for strings containing `$`
- [ ] 6.2 Apply `os.path.expandvars()` to each identified string before it is passed to the API
- [ ] 6.3 Add a test asserting that no config value written to the API contains a literal `$` character

## 7. MCP server pooling audit (D5)

- [ ] 7.1 Read `.claude-plugin/mcp.json` (ghostship consumer) and any MCP server configs inside crew containers
- [ ] 7.2 For each server that declares an `env` block, confirm whether it has per-session state
- [ ] 7.3 Add `"poolable": false` to any server with per-session state or credentials

## 8. Reload-in-place in `_ensure_crew_running` (D6, requires 1.2)

- [ ] 8.1 Once OQ-2 is resolved, locate the stop/start cycle in `_ensure_crew_running`
- [ ] 8.2 Replace with a reload-in-place call when the container is already running and only a config refresh is needed
- [ ] 8.3 Keep stop/start for the cold-boot path (container stopped or container does not exist)

## 9. Integration validation

- [ ] 9.1 Run `./install.sh` to rebuild images and restart transport
- [ ] 9.2 `launch` a new crew and confirm it reaches `ready` status without errors
- [ ] 9.3 `dispatch` a task to Ghost and confirm it completes
- [ ] 9.4 `pickup` the result and confirm it returns correctly
- [ ] 9.5 `nuke` the crew and confirm clean teardown
- [ ] 9.6 Run the transport test suite and confirm all tests pass
