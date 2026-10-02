# Tasks: TRN-186 Crew member registration

## 1. Proof of concept — verify member dispatch works

- [ ] 1.1 Add a single `config.agents` entry (e.g. `"ghost"`) to `_patch_crew_config` in `transport/lifecycle.py` and redeploy to academy
- [ ] 1.2 Launch a fresh crew and dispatch Ghost — verify it runs as a crew member session (check logs for `member_session_key` being set)
- [ ] 1.3 From inside that Ghost session (via a test task), call `spawn_run(agent="ghost", task="echo hello")` and confirm it succeeds without `member_identity_unavailable`
- [ ] 1.4 If 1.3 fails: investigate whether the Captain must dispatch Raven via the DM path (not headless) for `member_session_key` to be set — adjust design accordingly before proceeding

## 2. Register all 6 personas in config.agents

- [ ] 2.1 In `transport/lifecycle.py` `_patch_crew_config`, add `"agents"` dict to `full_overrides` for all 6 personas: ghost, spectre, banshee, wraith, reaper, raven
- [ ] 2.2 Verify deep-merge doesn't clobber the `default` agent — check `config.local.json` output after patching
- [ ] 2.3 Add unit tests in `tests/unit/test_lifecycle.py` asserting all 6 personas appear in the patched config with correct `kiro_agent`, `memory_store`, `session_control`, `member_dispatch` values

## 3. Update Raven agent spec

- [ ] 3.1 Add `"spawn_run"` to `allowedTools` in `academy/agents/raven.json`
- [ ] 3.2 Update Raven's prompt: remove the curl-based `POST /api/spawn` dispatch instructions and replace with `spawn_run` tool call instructions with the same intent marker pattern
- [ ] 3.3 Preserve all existing mailbox reading, dedup, and escalation logic — only the spawn mechanism changes

## 4. Update order templates

- [ ] 4.1 Update `academy/orders/spec-driven-development.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="<persona>", task="SDD dispatch <intent_id> ...")` instructions
- [ ] 4.2 Update `academy/orders/independent-review.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="wraith"/"banshee", task="REVIEW ...")` instructions
- [ ] 4.3 Remove `X-Internal-Secret` references from dispatch sections in both templates (keep maildeliver shell usage — that's unaffected)

## 5. End-to-end validation on academy

- [ ] 5.1 Deploy updated ghostship to academy (`./deploy.sh academy`)
- [ ] 5.2 Launch a fresh crew, seed it with the ghostship repo, start Captain with `sdd` template — verify Spectre is dispatched and runs to completion
- [ ] 5.3 Launch a fresh crew, start Captain with `independent-review` template — verify all 4 reviewers are dispatched (no `member_identity_unavailable`)
- [ ] 5.4 Run the e2e test suite: `GHOSTSHIP_E2E_URL=... GHOSTSHIP_API_KEY=... bash tests/run.sh --e2e`

## 6. Run unit tests and commit

- [ ] 6.1 Run `bash tests/run.sh --unit` and confirm all non-slow tests pass
- [ ] 6.2 Commit: `feat: register Ghostship personas as KiroCrew crew members (TRN-186)`
