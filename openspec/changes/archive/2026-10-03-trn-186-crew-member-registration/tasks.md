# Tasks: TRN-186 Crew member registration

## 1. config.agents entries in _patch_crew_config

- [x] 1.1 Add `config.agents` dict to `full_overrides` in `_patch_crew_config` — all 6 personas with `kiro_agent`, `memory_store: "default"`, `session_control: True`, `member_dispatch: True`; derived dynamically from composition manifest via `_load_crew_manifest`

## 2. _enroll_crew_members() — DM thread binding

- [x] 2.1 Implement `_enroll_crew_members(crew, crew_id, agent_names)`: calls `POST /api/members/{slug}/thread` via `_crew_api_with_recovery` for each deployed agent slug; idempotent, non-fatal
- [x] 2.2 Wire into fresh-launch path after gateway-ready
- [x] 2.3 Wire into stale-config recovery path after gateway-ready
- [x] 2.4 Wire into reboot recovery path after gateway-ready

## 3. Raven agent spec update

- [x] 3.1 Update Raven prompt: keep `POST /api/spawn` curl for dispatch but add `X-Session-Key: $KIRO_SESSION_ID` header — this passes attestation for enrolled sessions
- [x] 3.2 Keep all REST API usage for steer/continue/status unchanged
- [x] 3.3 Keep intent-UUID idempotency pattern and mailbox logic unchanged

## 4. Order templates update

- [x] 4.1 `academy/orders/spec-driven-development.md`: update dispatch to add `X-Session-Key: $KIRO_SESSION_ID` to curl calls
- [x] 4.2 `academy/orders/independent-review.md`: same update

## 5. PoC validation — Admiral validated

- [x] 5.1 Deployed to academy, enrolled 6 personas on poc-186 crew
- [x] 5.2 Verified "Member DM thread enrolled" in transport logs for all 6 personas
- [x] 5.3 Raven dispatched Ghost via `POST /api/spawn` with `X-Session-Key` → HTTP 200 confirmed (no `member_identity_unavailable`)

## 6. Follow-on work

Absorbed into TRN-187 (member-based dispatch):
- Dynamic enrolled_agents registry
- Unified slot routing via `_resolve_dispatch_slot`
- Clean slot naming (agent name, not member-agent)

## 7. Commit

- [x] 7.1 All changes committed across multiple commits on `release/0.6.0`
