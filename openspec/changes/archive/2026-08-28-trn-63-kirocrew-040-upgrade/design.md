## Context

See proposal.md — Why for the motivation. The transport currently runs against
KiroCrew 0.3.x. The four breaking API changes in 0.4.0 affect `transport/server.py`
in three clusters:

1. **Crew config API** — `_patch_crew_config` must add a required `agent` field,
   audit numeric fields for new bounds enforcement, and ensure no value contains
   an unexpanded `$VAR` string.

2. **Agents directory write-protection** — `_copy_agents` (and `_patch_models`,
   which also writes agent JSON files) must complete before KiroCrew 0.4.0 makes
   the agents directory read-only at runtime. The current setup order already
   calls `_copy_agents` in the post-restart window before `_patch_models`, which
   is fine. The risk is in `_ensure_crew_running`: it calls `_patch_crew_config`
   (config file write) but never `_copy_agents`; that path is unaffected.

3. **spawn_min_memory_gb workaround** — 0.4.0 fixes the config loader that
   previously ignored this field. The triple start/patch/stop/start workaround
   in `_ensure_crew_running` is now dead code and adds ~3s to every stopped-crew
   restart. Removing it is the main latency win.

Two additional changes are independent of the API breakages:

- **Containerfile base image pin** — two Containerfiles reference `0.3.0`
  explicitly and must be bumped.

- **MCP server poolability** — 0.4.0 pools env-declaring servers by default.
  A pre-change audit found zero env-declaring MCP server specs in the current
  ghostship agent files; the `poolable: false` addition may be a no-op but the
  audit is still required and should be recorded.

## Goals / Non-Goals

**Goals:**
- All four breaking API changes are addressed before any Containerfile pin is
  bumped, so a test build against the new image passes on first attempt.
- The spawn_min_memory_gb workaround is removed once the fix is confirmed.
- Containerfiles for `_base/admission` and `spec-ops` are pinned to `0.4.0`.
- Every env-declaring MCP server spec in the ghostship repo is audited; any
  stateful one gets `"poolable": false`.
- Full regression test pass: launch, dispatch, pickup, nuke.

**Non-Goals:**
- Adopting the reload-in-place endpoint to replace stop/start cycles. This is
  an optional improvement listed in the proposal; it is not a breaking change
  and is deferred to a follow-on change to keep this one focused on correctness.
- Changing any governance policy content — the `academy/policies/` templates are
  not touched by this change.

## Decisions

### 1. Add `agent` field via `_patch_crew_config`, not a new setup step

**Decision**: Inject `agent: <GA_CREW_AGENT>` into `config.local.json` inside
the existing `_patch_crew_config` call rather than adding a dedicated step.

**Rationale**: `_patch_crew_config` already owns `config.local.json` mutations.
Adding the field there keeps all config patching in one place and inherits the
existing error handling. An env var (`GA_CREW_AGENT`, default `"kiro"`) allows
operator override without a code change.

**Alternative considered**: A standalone `_inject_agent_field` step. Rejected
— adds a step and scatters config writes across the setup sequence.

### 2. Remove the spawn_min_memory_gb workaround entirely, not behind a flag

**Decision**: Delete the extra start/patch/stop/start block in
`_ensure_crew_running` unconditionally once the 0.4.0 Containerfile pin is in
place.

**Rationale**: The workaround comment already says "remove this block when
KiroCrew fixes the loader". 0.4.0 is that fix. Keeping a dead-code path behind
a flag adds maintenance surface and tempts a future reader to re-enable it.

**Alternative considered**: Guard with an env flag. Rejected — the workaround
is wrong against 0.4.0 (it causes an unnecessary extra restart cycle) not
merely redundant, so the flag would need to be explicitly set to disable broken
behaviour, which is worse than deletion.

### 3. Audit MCP poolability via static grep, not a runtime check

**Decision**: Audit `academy/agents/` and any crew manifest files for
`"env"` keys in server specs as part of the implementation task. Flag any match
for manual review; add `"poolable": false` where needed.

**Rationale**: The repo has a small, stable set of agent files. A static grep
at change time is simpler and cheaper than a runtime check, and changes to agent
files go through the same review process.

**Alternative considered**: A CI lint rule. Deferred — adds value for ongoing
hygiene but is out of scope for this correctness-focused change.

### 4. Containerfiles: bump `_base/admission` first, then `spec-ops`

**Decision**: Update `_base/admission/Containerfile` before `spec-ops/Containerfile`
because `spec-ops` `FROM`s `base-admission`, not the upstream image directly.

**Rationale**: Build order dependency — `spec-ops` resolves its FROM against the
locally built `localhost/base-admission:latest`. Bumping `_base/admission` first
ensures the next full build chain produces a consistent 0.4.0-based image.

### 5. Bounds audit: verify default env-var values, not arbitrary ranges

**Decision**: For each numeric field written by `_patch_crew_config`, verify
that the transport's default env-var value is within KiroCrew 0.4.0's documented
bounds. Document the bounds as inline comments in the patch script.

**Rationale**: The transport uses env vars as the operator-facing knobs, not the
raw config fields. Verifying defaults covers the common case. Operator-set
out-of-range values will be caught at launch time by the gateway's 4xx, which
surfaces a clear error — no extra transport-side validation is needed.

## Risks / Trade-offs

**[Risk] spawn_min_memory_gb workaround removal breaks 0.3.x compatibility**
→ The workaround removal is gated on the Containerfile pin bump. If someone
reverts the pin or runs the transport against a 0.3.x image, the field will
silently fall back to 4.0 GB (the old hardcoded default). Mitigation: the pin
bump and workaround removal are in the same commit and tested together.

**[Risk] GA_CREW_AGENT default "kiro" is wrong for some deployments**
→ If an operator's KiroCrew instance uses a different built-in agent name, crew
creation will fail at config validation. Mitigation: the env var is documented
in `docs/configuration.md` so operators can override it; the failure is a clear
4xx at launch time, not a silent misbehaviour.

**[Risk] MCP poolability audit misses a server added after this change**
→ Static grep covers the current state. A future env-declaring server added
without `"poolable": false` will be silently pooled. Mitigation: captured as a
follow-on CI lint rule task in the optional improvements section.

## Migration Plan

1. Read the 0.4.0 release notes and confirm the exact required `agent` field
   name and the enforced numeric bounds for each config field.
2. Make all `transport/server.py` changes (steps 1–3 above) with the existing
   `0.3.x` Containerfile pin still in place. Run unit tests to verify config
   patch output.
3. Bump both Containerfiles to `kirocrew:0.4.0`. Rebuild the image chain.
4. Run the full regression test pass: launch, dispatch, pickup, nuke.
5. If tests pass, the change is complete. If the workaround is still needed
   against 0.4.0 (unexpected), revert just the workaround deletion and file
   a bug against KiroCrew upstream.

**Rollback**: Revert `transport/server.py` and both Containerfiles to the
previous versions. The registry format is unchanged; existing crews are
unaffected by a rollback.

## Open Questions

None — all design decisions that would affect the spec or task breakdown have
been resolved above.
