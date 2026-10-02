# Tasks: TRN-186 Crew member registration

## 1. Add _enroll_crew_members() to transport/lifecycle.py

- [ ] 1.1 Add `_GHOSTSHIP_PERSONAS` constant: `["ghost", "spectre", "banshee", "wraith", "reaper", "raven"]`
- [ ] 1.2 Implement `_enroll_crew_members(podman, crew, crew_id)`: calls `POST /api/members/{slug}/thread` via `_crew_api_with_recovery` for each persona; logs success/failure; non-fatal on error
- [ ] 1.3 Wire `_enroll_crew_members()` into the launch path — call it after `_patch_crew_config()` at all 3 callsites where the config patch runs: line ~767 (provisional start recovery), line ~1448 (stopped-crew restart), and line ~1784 (fresh launch). In each case `_enroll_crew_members` must run after gateway-ready is confirmed.
- [ ] 1.4 Confirm `config.agents` entries (already added in PoC commit) are correct — verify the 6 persona entries are present in `full_overrides` in `_patch_crew_config`

## 2. Update Raven agent spec (academy/agents/raven.json)

- [ ] 2.1 Add `"spawn_run"` to `allowedTools`
- [ ] 2.2 Remove curl-based `POST /api/spawn` persona dispatch instructions from prompt
- [ ] 2.3 Replace with `spawn_run(agent="<persona>", task="...")` tool call instructions
- [ ] 2.4 Keep all REST API usage for steer/continue/status — those don't require attestation
- [ ] 2.5 Preserve all mailbox reading, intent-UUID dedup, and escalation logic unchanged

## 3. Update order templates

- [ ] 3.1 `academy/orders/spec-driven-development.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="<persona>", task="SDD dispatch <intent_id> ...")` instructions
- [ ] 3.2 `academy/orders/independent-review.md`: replace all `curl ... /api/spawn` dispatch blocks with `spawn_run(agent="wraith"/"banshee", task="REVIEW ...")` instructions
- [ ] 3.3 Remove `X-Internal-Secret` from dispatch sections only (keep for steer/continue/status)
- [ ] 3.4 Keep intent-UUID idempotency pattern (maildeliver before dispatching) intact

## 4. Add unit tests (tests/unit/test_lifecycle.py)

- [ ] 4.1 `test_patch_crew_config_has_agents_key` — all 6 personas in `full_overrides["agents"]`
- [ ] 4.2 `test_patch_crew_config_agents_correct_fields` — each entry has `kiro_agent`, `memory_store: "default"`, `session_control: True`, `member_dispatch: True`
- [ ] 4.3 `test_patch_crew_config_preserves_default_agent` — `"default"` entry not overwritten
- [ ] 4.4 `test_enroll_crew_members_calls_thread_endpoint` — verify `_crew_api_with_recovery` called with `POST /api/members/<slug>/thread` for each persona
- [ ] 4.5 `test_enroll_crew_members_non_fatal_on_error` — verify failure for one persona doesn't abort others

## 5. PoC validation — Admiral validates (requires deploy + live crew)

- [ ] 5.1 Deploy updated ghostship to academy (`cd ~/development/mcteamstar/terran/hyperv && ./deploy.sh academy`)
- [ ] 5.2 Launch a fresh crew — verify `_enroll_crew_members()` runs (check transport logs for "Member DM thread enrolled")
- [ ] 5.3 Dispatch Ghost with task: `echo "token: ${#KIROCREW_STUB_SESSION_TOKEN} chars"` — confirm token is non-empty; then attempt `spawn_run(agent="ghost", task="echo hello")` and confirm it succeeds without `member_identity_unavailable`

## 6. End-to-end validation — Admiral validates (requires live crew)

- [ ] 6.1 Launch a fresh crew, seed it, start Captain with `sdd` template — verify Spectre dispatched and runs to completion
- [ ] 6.2 Launch a fresh crew, start Captain with `independent-review` template — verify all 4 reviewers dispatched successfully
- [ ] 6.3 Run unit tests: `bash tests/run.sh --unit`

## 7. Commit

- [ ] 7.1 Commit all changes: `feat: register Ghostship personas as KiroCrew crew members (TRN-186)`
