# Tasks: TRN-186 Crew member registration

## 1. Proof of concept — verify stub token stamping

The critical unknown: does `config.agents` registration alone (no `member_id`
enrollment) cause the gateway to stamp `KIROCREW_STUB_SESSION_TOKEN` on the
spawned process env? This gates whether Phase 2b (`_enroll_crew_members`) is needed.

- [ ] 1.1 Add all 6 `config.agents` entries to `_patch_crew_config` in `transport/lifecycle.py` (see design section 1)
- [ ] 1.2 Deploy to academy (`./deploy.sh academy`)
- [ ] 1.3 Launch a fresh crew, dispatch Ghost with task: `echo "token: $KIROCREW_STUB_SESSION_TOKEN" && spawn_run(agent="ghost", task="echo hello")` — check if `KIROCREW_STUB_SESSION_TOKEN` is non-empty and if `spawn_run` succeeds without `member_identity_unavailable`
- [ ] 1.4 If token IS present and spawn_run succeeds: Phase 2b not needed, proceed to task 2
- [ ] 1.5 If token is absent or spawn_run fails: add `_enroll_crew_members()` (design section 2) called after `_wait_for_gateway_ready()`, redeploy, and repeat 1.3

## 2. Register all 6 personas in config.agents (lifecycle.py)

- [ ] 2.1 In `transport/lifecycle.py` `_patch_crew_config`, add `"agents"` dict to `full_overrides` for all 6 personas with fields: `kiro_agent`, `memory_store: "default"`, `session_control: True`, `member_dispatch: True`
- [ ] 2.2 Verify deep-merge doesn't clobber the `default` agent — inspect `config.local.json` after patching on a live crew
- [ ] 2.3 If PoC 1.5 required: implement `_enroll_crew_members()` and wire it into the launch path after gateway-ready
- [ ] 2.4 Add unit tests in `tests/unit/test_lifecycle.py`:
  - All 6 personas present in `full_overrides["agents"]`
  - Each has correct `kiro_agent`, `memory_store`, `session_control`, `member_dispatch`
  - `default` agent entry is not overwritten by the merge

## 3. Update Raven agent spec

- [ ] 3.1 Add `"spawn_run"` to `allowedTools` in `academy/agents/raven.json`
- [ ] 3.2 Remove curl-based `POST /api/spawn` persona dispatch instructions from Raven's prompt
- [ ] 3.3 Replace with `spawn_run(agent="<persona>", task="...")` tool call instructions
- [ ] 3.4 Keep all REST API usage for status/steer/continue — those don't require attestation
- [ ] 3.5 Preserve all mailbox reading, intent-UUID dedup, and escalation logic unchanged

## 4. Update order templates

- [ ] 4.1 `academy/orders/spec-driven-development.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="<persona>", task="SDD dispatch <intent_id> ...")` instructions
- [ ] 4.2 `academy/orders/independent-review.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="wraith"/"banshee", task="REVIEW ...")` instructions
- [ ] 4.3 Remove `X-Internal-Secret` references from dispatch sections in both templates
- [ ] 4.4 Keep maildeliver/intent-UUID pattern intact — only the spawn mechanism changes

## 5. End-to-end validation on academy

- [ ] 5.1 Deploy updated ghostship to academy
- [ ] 5.2 Launch a fresh crew, seed it, start Captain with `sdd` template — verify Spectre is dispatched and runs to completion without `member_identity_unavailable`
- [ ] 5.3 Launch a fresh crew, start Captain with `independent-review` template — verify all 4 reviewers dispatched successfully
- [ ] 5.4 Run unit tests: `bash tests/run.sh --unit`

## 6. Commit

- [ ] 6.1 Commit all changes: `feat: register Ghostship personas as KiroCrew crew members (TRN-186)`
