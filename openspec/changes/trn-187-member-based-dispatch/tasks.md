# Tasks: TRN-187 Member-based dispatch

## 1. Store enrolled agents in crew registry

- [ ] 1.1 In `transport/lifecycle.py`, after `_enroll_crew_members()` in the fresh-launch path, write `enrolled_agents` (list of slugs) into the crew's registry entry
- [ ] 1.2 In the recovery paths (stale-config restart, reboot recovery), after `_enroll_crew_members()`, update `enrolled_agents` in the registry

## 2. Extract _resolve_dispatch_slot helper

- [ ] 2.1 In `transport/lifecycle.py`, implement `_resolve_dispatch_slot(agent, slot, crew)` → `(effective_slot, parent_session)` as described in design.md
- [ ] 2.2 Update `_dispatch_tasks()` in `lifecycle.py` to use `_resolve_dispatch_slot()` — remove the inline slot resolution and per-task `_GHOSTSHIP_PERSONAS` check
- [ ] 2.3 Update `dispatch()` in `server.py` to use `_resolve_dispatch_slot()` — remove the inline slot resolution and per-task `_GHOSTSHIP_PERSONAS` check

## 3. Update dispatch() slot param documentation

- [ ] 3.1 Update the `slot` parameter docstring in `server.py`'s `dispatch()` to document: persona agents default to their member DM slot; `slot="bridge"` bypasses attestation; `slot="member-<slug>"` is the explicit equivalent
- [ ] 3.2 Update the `dispatch` tool description in the MCP tool registration to reflect new slot semantics

## 4. Tests

- [ ] 4.1 Add/update unit tests for `_resolve_dispatch_slot`: persona agent with no slot → member slot; non-persona agent on dashboard crew → bridge; explicit slot → respected; enrolled_agents registry fallback
- [ ] 4.2 Add test: crew with `enrolled_agents` in registry routes custom agent to member slot
- [ ] 4.3 Add test: crew without `enrolled_agents` falls back to `_GHOSTSHIP_PERSONAS`

## 5. Validation

- [ ] 5.1 Run `bash tests/run.sh --unit` — all non-slow tests pass
- [ ] 5.2 Deploy to academy, launch a crew with `dashboard=True`, dispatch a persona — confirm `slot: "member-<persona>"` in response
- [ ] 5.3 Dispatch a persona from Raven via curl with `X-Session-Key: $KIRO_SESSION_ID` — confirm HTTP 200

## 6. Commit

- [ ] 6.1 Commit: `feat: member-based dispatch — dynamic enrollment and unified slot routing (TRN-187)`
