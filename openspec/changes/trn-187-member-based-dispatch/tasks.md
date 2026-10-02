# Tasks: TRN-187 Member-based dispatch

## 1. Store enrolled agents in crew registry

- [ ] 1.1 In `transport/lifecycle.py`, after `_enroll_crew_members()` in the fresh-launch path, write `enrolled_agents` (list of slugs) into the crew's registry entry
- [ ] 1.2 In the recovery paths (stale-config restart, reboot recovery), after `_enroll_crew_members()`, update `enrolled_agents` in the registry

## 2. Extract _resolve_dispatch_slot helper

- [ ] 2.1 In `transport/lifecycle.py`, implement `_resolve_dispatch_slot(agent, slot, crew)` — enrolled agents route to member DM slot (echoing agent name), unenrolled get bridge/headless; no `_GHOSTSHIP_PERSONAS` fallback
- [ ] 2.2 Update `_dispatch_batch()` in `lifecycle.py` to use `_resolve_dispatch_slot()` — remove inline slot resolution
- [ ] 2.3 Update `dispatch()` in `server.py` to use `_resolve_dispatch_slot()` — remove inline slot resolution; remove `_GHOSTSHIP_PERSONAS` import

## 3. Update dispatch() slot param documentation

- [ ] 3.1 Update the `slot` parameter docstring in `server.py`'s `dispatch()` to document: persona agents default to their member DM slot; `slot="bridge"` bypasses attestation; `slot="member-<slug>"` is the explicit equivalent
- [ ] 3.2 Update the `dispatch` tool description in the MCP tool registration to reflect new slot semantics
- [ ] 3.3 Update the `dispatch` tool description in `.claude-plugin/skills/ghostship-command/SKILL.md` — the slot semantics change is Admiral-visible

## 4. Tests

- [ ] 4.1 Add `enrolled_agents` to crew fixtures in `test_dispatch_slot.py` and `test_server.py`
- [ ] 4.2 Update slot assertions: enrolled agent + no slot → agent name (e.g. `"ghost"`), not `"member-ghost"`
- [ ] 4.3 Add test: unenrolled agent (no `enrolled_agents` key) on dashboard crew → `"bridge"`
- [ ] 4.4 Add test: unenrolled agent on non-dashboard crew → `None` (headless)

## 5. Validation — Admiral validates (requires deploy + live crew)

- [ ] 5.1 Run `bash tests/run.sh --unit` — all non-slow tests pass
- [ ] 5.2 Deploy to academy, launch a crew with `dashboard=True`, dispatch a persona — confirm `slot: "member-<persona>"` in response
- [ ] 5.3 Dispatch a persona from Raven via curl with `X-Session-Key: $KIRO_SESSION_ID` — confirm HTTP 200

## 6. Commit

- [ ] 6.1 Commit: `feat: member-based dispatch — dynamic enrollment and unified slot routing (TRN-187)`
