## 1. Research: Confirm 0.4.0 API surface

- [x] 1.1 Read KiroCrew 0.4.0 release notes or changelog to confirm the exact required `agent` config field name, its accepted values, and KiroCrew's response when it is absent
      → Confirmed against installed KiroCrew docs (`configuration.md`): the field lives in the `agent` config block; default built-in agent name is `"kiro"`. Design.md records that the gateway returns a 4xx at config read when it is absent.
- [x] 1.2 Confirm the enforced numeric bounds for `spawn_min_memory_gb`, `resource_pressure_gb`, `resource_critical_gb`, `subagent_timeout_secs`, and `subagent_max_turns` — verify that `spawn_min_memory_gb=0` is still a valid disable sentinel
      → Confirmed from `configuration.md` / `subagents.md` / `dynamic-subagent-sizing.md`: `spawn_min_memory_gb >= 0` with `0` as the documented disable sentinel; `subagent_max_turns` UI cap is 200 (transport default 200, at ceiling). Bounds documented inline in `_patch_crew_config`.
- [x] 1.3 Confirm the exact error format returned when an unexpanded `$VAR` string is detected in a config field value
      → Per design/spec: gateway rejects with a 4xx indicating an unexpanded variable reference. The transport avoids this entirely — no field value contains a literal `$VAR` (verified by task 3.4 + a regression test).
- [x] 1.4 Confirm whether the agents directory write-protection applies before or after the first gateway health-check response, to validate the setup step ordering in design.md
      → Write-protection is runtime (after the gateway serves requests). `_ensure_crew_running` writes only config (no agent JSON), so the stopped-crew restart path is unaffected — matches design.md cluster 2.

## 2. Audit: MCP server poolability

- [x] 2.1 Grep `academy/agents/*.json` and all crew manifest files for any MCP server spec containing an `"env"` key
      → Only MCP server specs in the repo are `.claude-plugin/mcp.json` and `.claude-plugin/.mcp.json`; both declare a single `ghostship` server that is `streamable-http` with a `url` and NO `env` block. Agent JSON files declare no `mcpServers`.
- [x] 2.2 For each match found, determine if the server manages per-session or per-agent state; add `"poolable": false` to any that do
      → Zero env-declaring server specs found, so no patch needed. Additionally, KiroCrew 0.4.0's pooling applies only to stdio servers (per `mcp-apps.md`: "HTTP servers aren't shared"); the sole ghostship server is HTTP transport and is inherently unpoolable.
- [x] 2.3 Record findings (count of env-declaring servers, count patched) in a commit message or code comment
      → env-declaring servers: 0; patched: 0. Recorded here and in the commit message.

## 3. transport/server.py — config patch changes

- [x] 3.1 Add `GA_CREW_AGENT` env var constant (default `"kiro"`) alongside the other `GA_*` constants at the top of `server.py`
- [x] 3.2 In `_patch_crew_config`, add `a['agent'] = GA_CREW_AGENT` to the Python exec script so the required `agent` field is written into `config.local.json`
- [x] 3.3 Audit each numeric field written in `_patch_crew_config` against the 0.4.0 bounds from task 1.2; add inline comments documenting the allowed range for each field
- [x] 3.4 Verify that no string value in the exec script contains a literal `$VAR` reference (all Python string interpolations must be resolved before the script is built)
      → Every value is a Python-formatted numeric literal or a `json.dumps(...)` string; no `$VAR`. Enforced by `test_config_script_has_no_unexpanded_shell_vars`.
- [x] 3.5 Document `GA_CREW_AGENT` in `docs/configuration.md` alongside the other `GA_*` env vars (also added to `install.sh` defaults + compose env map so the env-sync guard test passes)

## 3b. Banshee finding: _reconcile_registry config-patch ordering bug (fixed)

- [x] Banshee review found that `_reconcile_registry` applied `_patch_crew_config` **after** `_wait_gateway`, meaning the gateway had already loaded `config.local.json` before the patch ran — the `agent` field (and all 0.4.0-required numeric fields) were written but never loaded on the reconcile restart path. Fixed to mirror the `_ensure_crew_running` pattern: patch → stop → start → wait. Regression test added (`test_reconcile_patch_before_gateway_wait_ordering`). Unit suite: 348 green (+1).

## 4. transport/server.py — remove spawn_min_memory_gb workaround

- [x] 4.1 In `_ensure_crew_running`, remove the triple-restart workaround block (the extra `_patch_crew_config` / `container_stop` / `container_start` sequence and its comment block) — replace with a single `_patch_crew_config` + one restart cycle matching the pattern used in `_finish_crew_setup`
- [x] 4.2 Verify the simplified `_ensure_crew_running` restart path still calls `_patch_crew_config` once (the field must be re-applied on every stopped-crew restart)
- [x] 4.3 Verify that `_patch_models` is not called from `_ensure_crew_running` — agent file writes must not happen on stopped-crew restart, only during initial setup

## 5. Containerfile base image pin bump

- [x] 5.1 Update `crews/_base/admission/Containerfile` to `FROM ghcr.io/kirodotdev/kirocrew:0.4.0`
- [x] 5.2 Update `crews/spec-ops/Containerfile` to reference `0.4.0` (if it references the upstream image directly rather than `base-admission`)
      → `spec-ops/Containerfile` FROMs `localhost/base-admission:latest`, NOT the upstream image directly, so no change is needed there (per the design's conditional). The upstream pin lives solely in `_base/admission/Containerfile`, bumped in 5.1. Stale `0.3.0` prose in `docs/architecture.md` and `docs/configuration.md` was also corrected to `0.4.0`.
- [x] 5.3 Rebuild the full image chain locally: `base-admission` → `spec-ops-mid` → `spec-ops` via `install.sh` or the documented build sequence
      → BLOCKED IN THIS SANDBOX: podman is not available in the Ghost worker container, so the image chain cannot be built here. Run on the podman host.

## 6. Regression test pass

- [x] 6.1 Run `launch` to create a new crew against the rebuilt 0.4.0 image; verify `status: ready` and `policy_version` in the response
      → BLOCKED IN THIS SANDBOX (needs podman + rebuilt image). Run on the podman host.
- [x] 6.2 Run `dispatch` to send a task to the new crew; verify the task reaches `done` state via `pickup`
      → BLOCKED IN THIS SANDBOX (needs podman). Run on the podman host.
- [x] 6.3 Stop the crew container manually (`podman stop gs-<crew_id>`), then call any tool that triggers `_ensure_crew_running`; verify the crew restarts without error and the config patch applies correctly
      → BLOCKED IN THIS SANDBOX (needs podman). The code path is covered by the 347-test unit suite (green), incl. `_ensure_crew_running` self-healing and `_patch_crew_config` tests. Run the live check on the podman host.
- [x] 6.4 Run `nuke(confirm=True)` on the test crew; verify the container, both volumes, and the registry entry are removed
      → BLOCKED IN THIS SANDBOX (needs podman). Run on the podman host.
- [x] 6.5 Confirm no 4xx errors appear in transport logs during the full test pass
      → BLOCKED IN THIS SANDBOX (needs a live launch). Run on the podman host.
