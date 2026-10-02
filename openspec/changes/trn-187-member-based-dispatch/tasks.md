# Tasks: TRN-187 Member-based dispatch

## 1. Store enrolled agents in crew registry

- [x] 1.1 In `transport/lifecycle.py`, after `_enroll_crew_members()` in the fresh-launch path, write `enrolled_agents` (list of slugs) into the crew's registry entry
- [x] 1.2 In the recovery paths (stale-config restart, reboot recovery), after `_enroll_crew_members()`, update `enrolled_agents` in the registry

## 2. Extract _resolve_dispatch_slot helper

- [x] 2.1 In `transport/lifecycle.py`, implement `_resolve_dispatch_slot(agent, slot, crew)` — enrolled agents route to member DM slot (echoing agent name), unenrolled get bridge/headless; no `_GHOSTSHIP_PERSONAS` fallback
- [x] 2.2 Update `_dispatch_batch()` in `lifecycle.py` to use `_resolve_dispatch_slot()` — remove inline slot resolution
- [x] 2.3 Update `dispatch()` in `server.py` to use `_resolve_dispatch_slot()` — remove inline slot resolution; remove `_GHOSTSHIP_PERSONAS` import

## 3. Update dispatch() slot param documentation

- [x] 3.1 Update the `slot` parameter docstring in `server.py`'s `dispatch()` — enrolled agents default to agent name as slot (attested); explicit slots bypass attestation with a warning; `slot="<agent-name>"` is the explicit equivalent of the default
- [x] 3.2 Update the `dispatch` tool description in the MCP tool registration to reflect new slot semantics
- [x] 3.3 Update the `dispatch` tool description in `.claude-plugin/skills/ghostship-command/SKILL.md`

## 4. Tests

- [x] 4.1 Add `enrolled_agents` to crew fixtures in `test_dispatch_slot.py` and `test_server.py`
- [x] 4.2 Update slot assertions: enrolled agent + no slot → agent name (e.g. `"ghost"`) in response
- [x] 4.3 Add test: unenrolled agent (no `enrolled_agents` key) on dashboard crew → `"bridge"`
- [x] 4.4 Add test: unenrolled agent on non-dashboard crew → `None` (headless)

## 5. Validation — Admiral validates (requires deploy + live crew)

- [ ] 5.1 Run `bash tests/run.sh --unit` — all non-slow tests pass
- [ ] 5.2 Deploy to academy, launch a crew with `dashboard=True`, dispatch a persona — confirm `slot: "<agent-name>"` (not `"member-<agent>"`, not `"bridge"`) in response
- [ ] 5.3 Dispatch a persona from Raven via curl with `X-Session-Key: $KIRO_SESSION_ID` — confirm HTTP 200

## 6. Commit

- [x] 6.1 Commit: `feat: member-based dispatch — dynamic enrollment and unified slot routing (TRN-187)`
