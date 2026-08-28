## 1. Research: Confirm 0.4.0 API surface

- [ ] 1.1 Read KiroCrew 0.4.0 release notes or changelog to confirm the exact required `agent` config field name, its accepted values, and KiroCrew's response when it is absent
- [ ] 1.2 Confirm the enforced numeric bounds for `spawn_min_memory_gb`, `resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, and `subagent_max_turns` — verify that `spawn_min_memory_gb=0` is still a valid disable sentinel
- [ ] 1.3 Confirm the exact error format returned when an unexpanded `$VAR` string is detected in a config field value
- [ ] 1.4 Confirm whether the agents directory write-protection applies before or after the first gateway health-check response, to validate the setup step ordering in design.md

## 2. Audit: MCP server poolability

- [ ] 2.1 Grep `academy/agents/*.json` and all crew manifest files for any MCP server spec containing an `"env"` key
- [ ] 2.2 For each match found, determine if the server manages per-session or per-agent state; add `"poolable": false` to any that do
- [ ] 2.3 Record findings (count of env-declaring servers, count patched) in a commit message or code comment

## 3. transport/server.py — config patch changes

- [ ] 3.1 Add `GA_CREW_AGENT` env var constant (default `"kiro"`) alongside the other `GA_*` constants at the top of `server.py`
- [ ] 3.2 In `_patch_crew_config`, add `a['agent'] = GA_CREW_AGENT` to the Python exec script so the required `agent` field is written into `config.local.json`
- [ ] 3.3 Audit each numeric field written in `_patch_crew_config` against the 0.4.0 bounds from task 1.2; add inline comments documenting the allowed range for each field
- [ ] 3.4 Verify that no string value in the exec script contains a literal `$VAR` reference (all Python string interpolations must be resolved before the script is built)
- [ ] 3.5 Document `GA_CREW_AGENT` in `docs/configuration.md` alongside the other `GA_*` env vars

## 4. transport/server.py — remove spawn_min_memory_gb workaround

- [ ] 4.1 In `_ensure_crew_running`, remove the triple-restart workaround block (the extra `_patch_crew_config` / `container_stop` / `container_start` sequence and its comment block) — replace with a single `_patch_crew_config` + one restart cycle matching the pattern used in `_finish_crew_setup`
- [ ] 4.2 Verify the simplified `_ensure_crew_running` restart path still calls `_patch_crew_config` once (the field must be re-applied on every stopped-crew restart)
- [ ] 4.3 Verify that `_patch_models` is not called from `_ensure_crew_running` — agent file writes must not happen on stopped-crew restart, only during initial setup

## 5. Containerfile base image pin bump

- [ ] 5.1 Update `crews/_base/admission/Containerfile` to `FROM ghcr.io/kirodotdev/kirocrew:0.4.0`
- [ ] 5.2 Update `crews/spec-ops/Containerfile` to reference `0.4.0` (if it references the upstream image directly rather than `base-admission`)
- [ ] 5.3 Rebuild the full image chain locally: `base-admission` → `spec-ops-mid` → `spec-ops` via `install.sh` or the documented build sequence

## 6. Regression test pass

- [ ] 6.1 Run `launch` to create a new crew against the rebuilt 0.4.0 image; verify `status: ready` and `policy_version` in the response
- [ ] 6.2 Run `dispatch` to send a task to the new crew; verify the task reaches `done` state via `pickup`
- [ ] 6.3 Stop the crew container manually (`podman stop gs-<crew_id>`), then call any tool that triggers `_ensure_crew_running`; verify the crew restarts without error and the config patch applies correctly
- [ ] 6.4 Run `nuke(confirm=True)` on the test crew; verify the container, both volumes, and the registry entry are removed
- [ ] 6.5 Confirm no 4xx errors appear in transport logs during the full test pass
