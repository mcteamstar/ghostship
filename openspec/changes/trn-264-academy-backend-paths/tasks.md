# Tasks

## 1. Prepare mcteamstar/.agents for container use

- [x] 1.1 Audit `setup` for container-hostile behaviour: harness-not-found handling, symlink creation, any macOS-specific paths — verify `setup kiro`, `setup claude` each exit 0 inside a container with only kiro-cli installed
- [x] 1.2 Ensure `setup <backend>` silently skips uninstalled harnesses rather than erroring — verify with `setup claude` in a container that has no `claude` binary
- [x] 1.3 Tag or pin the commit to use in the Containerfile — verify the pinned ref exists on `mcteamstar/.agents`

## 2. Bake .agents into crew images

- [x] 2.1 Add `git clone --depth 1 <ref> /home/kirocrew/.agents` step to `crews/spec-ops/Containerfile` (as kirocrew user or with chown) — verify `/home/kirocrew/.agents/setup` exists and is executable in the built image
- [x] 2.2 Add the same step to any other composition Containerfiles — verify for each image
- [x] 2.3 Add `.agents` to the crew image label or a build arg so stale `.agents` triggers a rebuild when the pinned ref changes

## 3. Refactor AcademyLoader

- [x] 3.1 Add `acp_backend` parameter to `AcademyLoader.__init__()` and thread it through from `_finish_crew_setup` in `lifecycle.py` (registry entry already carries `acp_backend`) — verify existing kiro crews still launch correctly
- [x] 3.2 Implement `_stage_skills()`: tar-inject manifest-selected skills into `/home/kirocrew/.agents/skills/` — verify files appear in the container under `.agents/skills/`
- [x] 3.3 Implement `_stage_steering()`: tar-inject manifest-selected steering docs into `/home/kirocrew/.agents/context/` — verify files appear in the container under `.agents/context/`
- [x] 3.4 Implement `_stage_mcp()`: resolve catalogue entries (env-var substitution unchanged), write a single `.agents/mcp/servers.json` containing all resolved entries with `"disabled": false` — verify the file appears in the container under `.agents/mcp/servers.json`
- [x] 3.5 Implement `_run_setup()`: exec `.agents/setup <backend>` inside the container after all staging is complete — verify exit code 0 for kiro backend on a test crew
- [x] 3.6 Update `copy_all()` to call stage methods + `_run_setup()` instead of the old per-kind copy methods — verify kiro crew launch end-to-end: skills in `~/.kiro/skills/`, steering in `~/.kiro/steering/`, mcp.json written
- [x] 3.7 Retain persona JSON delivery (`_copy_agents()` → `~/.kiro/agents/`) for kiro backend only; skip for claude/codex — verify no `~/.kiro/agents/` writes occur on a claude-backend crew
- [x] 3.8 Update unit tests in `tests/unit/` for `AcademyLoader` to cover the new staging path and `_run_setup()` — verify `pytest tests/unit/` passes

## 4. Verify claude backend delivery

- [ ] 4.1 Launch a claude-backend crew and confirm skills land in `~/.claude/skills/` inside the container — verify with `podman exec <container> ls /home/kirocrew/.claude/skills/`
- [ ] 4.2 Confirm steering docs land in `~/.claude/rules/` — verify with `podman exec`
- [ ] 4.3 Confirm MCP config is written to `~/.claude.json` (or the backend-appropriate location per `.agents/setup`) — verify with `podman exec`
- [ ] 4.4 Dispatch a wraith on the claude crew and confirm academy skills appear in its Skill list — verify skill names match the manifest selection

## 5. Update specs and docs

- [x] 5.1 Update `docs/agents.md` or relevant docs to reflect that academy delivery now targets the backend's native paths — verify the docs describe the correct paths per backend
- [ ] 5.2 Update `crew-steering` main spec at `openspec/specs/crew-steering/spec.md` — will be handled by archive; no manual edit needed here

## Workflow follow-up

- Run `/assimilate` to sync the modified capability specs (`crew-steering`, `mcp-server-config`) and archive this change.
