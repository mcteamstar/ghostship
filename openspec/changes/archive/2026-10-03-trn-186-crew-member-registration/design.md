# Design: TRN-186 Crew member registration

## How stub token stamping actually works (confirmed by research + PoC)

The `KIROCREW_STUB_SESSION_TOKEN` env var is only present in a session's MCP
server process if the session was started as a **member DM thread**. The token
is stamped by `member_dispatch_session_server()` in `members.py`, which builds
a session-level MCP server entry that includes the token. This function is only
called for sessions whose slot key starts with `member-` (i.e. proper member DM
threads, not headless spawns).

**config.agents alone does not cause token stamping.** It is a config
declaration only — it tells the gateway what kiro_agent to use when a session
IS opened on that member's slot, but it does not create the DM binding or open
the session.

**What creates the DM binding:** `POST /api/members/{slug}/thread` — the
idempotent get-or-create endpoint. This writes `dm.json` (via `write_dm_binding`)
which binds the slug to the crew member name and slot key. Once the binding
exists, sessions opened on that slot are treated as member DM threads and get
the token stamped.

**The transport can call this endpoint.** The transport holds an owner-level
dashboard cookie (`mc_token_<port>`), minted via `kirocrew token --ttl 24h` exec
inside the container then exchanged at `GET /?token=...`. This is completely
independent of `dashboard=True/False` — it's a direct container exec path.
The `/api/members/{slug}/thread` endpoint passes both gates:
1. `_deny_app_caller` → passes (mc_token is not an app token)
2. `require_owner_dashboard_request` → passes (mc_token is owner dashboard auth)

**The correct approach:**

```
At crew launch (after gateway-ready):
  transport calls POST /api/members/{slug}/thread for each of the 6 personas
    → creates dm.json binding for each
    → slot key "member-raven" is now bound to the "raven" crew member

Captain dispatches Raven (still via /api/spawn, cookie auth, no change):
  → gateway starts kiro-cli session on slot "member-raven"
  → session IS a member DM thread (binding exists)
  → member_dispatch_session_server() IS called
  → KIROCREW_STUB_SESSION_TOKEN IS stamped in Raven's MCP server env

Raven uses spawn_run MCP tool:
  → mcp_tools/spawn.py reads KIROCREW_STUB_SESSION_TOKEN from env
  → _post("/api/spawn") sends X-Session-Token + X-Session-Key + X-Internal-Secret
  → session_key_is_attested() returns True
  → Spectre/Banshee/Wraith spawned ✓
```

---

## 1. config.agents entries (prerequisite for thread enrollment)

`_patch_crew_config` adds this to `full_overrides` in `lifecycle.py`.
**Required** so the gateway recognises the slug → member name mapping when
`POST /api/members/{slug}/thread` is called:

```python
"agents": {
    "ghost":   {"kiro_agent": "ghost",   "memory_store": "default", "session_control": True, "member_dispatch": True},
    "spectre": {"kiro_agent": "spectre", "memory_store": "default", "session_control": True, "member_dispatch": True},
    "banshee": {"kiro_agent": "banshee", "memory_store": "default", "session_control": True, "member_dispatch": True},
    "wraith":  {"kiro_agent": "wraith",  "memory_store": "default", "session_control": True, "member_dispatch": True},
    "reaper":  {"kiro_agent": "reaper",  "memory_store": "default", "session_control": True, "member_dispatch": True},
    "raven":   {"kiro_agent": "raven",   "memory_store": "default", "session_control": True, "member_dispatch": True},
}
```

`config.local.json` deep-merges over `config.json` — the `"default"` agent
entry is preserved.

## 2. _enroll_crew_members() — DM thread binding

Called from the launch path after `_wait_for_gateway_ready()` and after
`_patch_crew_config()`. Uses the same `_crew_api_with_recovery` mechanism
the transport already uses for all gateway calls. Idempotent — thread is
a get-or-create.

```python
_GHOSTSHIP_PERSONAS = ["ghost", "spectre", "banshee", "wraith", "reaper", "raven"]

def _enroll_crew_members(podman: PodmanClient, crew: dict, crew_id: str) -> None:
    """Create member DM thread bindings for all 6 Ghostship personas.

    POST /api/members/{slug}/thread is idempotent (get-or-create). Once a
    binding exists the gateway stamps KIROCREW_STUB_SESSION_TOKEN into the
    session's MCP server env, enabling spawn_run attestation from within
    that session.

    Called after gateway-ready and after _patch_crew_config so config.agents
    entries exist before the gateway resolves the slug → member mapping.
    Failures are logged but not fatal — the crew still launches; spawning
    will fall back to the pre-0.7.0 failure mode for unenrolled personas.
    """
    for slug in _GHOSTSHIP_PERSONAS:
        try:
            _crew_api_with_recovery(
                podman, crew, crew_id, "POST", f"/api/members/{slug}/thread"
            )
            logger.info("Member DM thread enrolled for %s on crew %s", slug, crew_id)
        except Exception as e:
            logger.warning(
                "Member enrollment failed for %s on crew %s: %s", slug, crew_id, e
            )
```

## 3. spawn_run tool in Raven

`academy/agents/raven.json`:
- Add `"spawn_run"` to `allowedTools`
- Remove curl-based `POST /api/spawn` persona dispatch instructions from prompt
- Replace with `spawn_run(agent="<persona>", task="...")` instructions
- Keep REST API usage for status/steer/continue — those don't require attestation

## 4. Order template changes

### spec-driven-development.md
Replace all `curl -X POST .../api/spawn -H "X-Internal-Secret: ..."` dispatch
blocks with `spawn_run` tool call instructions:
```
Use the spawn_run tool: spawn_run(agent="spectre", task="SDD dispatch <intent_id> <change> ...")
```
Keep the intent-UUID idempotency pattern (maildeliver before dispatching) — unchanged.
Keep `X-Internal-Secret` usage for steer/continue/status REST calls — unchanged.

### independent-review.md
Same pattern — replace `/api/spawn` curl dispatches with `spawn_run`.

## 5. Captain dispatch of Raven — no change needed

The Captain dispatches Raven via the transport's external `/api/spawn`. That
call uses cookie auth (owner dashboard). The gateway will start Raven on its
member DM slot `member-raven` (because the binding exists after enrollment).
No change needed to the Captain order or the transport's dispatch mechanism.

## 6. What does NOT change

- Transport cookie auth (still correct for all operations)
- Intent-UUID idempotency pattern in order templates
- Agent spec content except raven.json `allowedTools` + prompt dispatch section
- The 5 other `academy/agents/` JSON files
- Attestation mechanism (no KiroCrew changes)
- REST steer/continue/status calls from Raven (no attestation needed)

## Open questions (none blocking)

None. The full chain is confirmed by source code investigation. PoC confirmed
`config.agents` alone is insufficient; the DM thread binding is the correct
and only required enrollment step.
