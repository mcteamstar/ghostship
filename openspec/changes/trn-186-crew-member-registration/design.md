# Design: TRN-186 Crew member registration

## Background: how attestation actually works

The research investigation (5 Wraith angles + consolidation, see
`research/trn-186-consolidated-architecture.md`) confirmed the exact token
flow and corrected several assumptions in the initial design.

**Transport auth path:** The transport uses cookie auth (`mc_token_5476`),
not `X-Internal-Secret`. It is a dashboard-owner caller, not an internal caller.
This means the transport cannot directly obtain a session token — it has no
`KIROCREW_STUB_SESSION_TOKEN` in its environment.

**Why Raven's current spawns fail — confirmed chain:**
1. Transport dispatches Raven via cookie auth → gateway does not stamp
   `KIROCREW_STUB_SESSION_TOKEN` into Raven's MCP process env
2. Raven calls curl `/api/spawn` → `KIROCREW_STUB_SESSION_TOKEN` absent →
   `X-Session-Token` empty → `session_key_is_attested()` returns False → 409

**Why `spawn_run` works where curl doesn't:**
`mcp_tools/spawn.py` → `mcp_core._post()` → `_session_token_header()` reads
`KIROCREW_STUB_SESSION_TOKEN` from the MCP process env and sends it as
`X-Session-Token` alongside `X-Session-Key` and `X-Internal-Secret`. The MCP
server process has the token in its env (stamped at session start by the
gateway). Curl run from the shell tool inherits the same env, but curl would
also need to construct `X-Session-Key` via HMAC lookup — `spawn_run` handles
all of this transparently.

**Critical unknown:** Does `config.agents` registration alone (no full
`member_id` enrollment) cause the gateway to stamp `KIROCREW_STUB_SESSION_TOKEN`
into the spawned process env? If not, a `_enroll_crew_members()` step is needed
after gateway-ready (Phase 2b). The PoC (task 1.x) answers this definitively.

---

## 1. config.agents entries

`_patch_crew_config` adds this to `full_overrides` in `lifecycle.py`:

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

`kiro_agent` matches the filename in `/agents/` (without `.json`). The gateway
resolves agent specs from that directory keyed by name.

`config.local.json` is deep-merged over `config.json` by the gateway — the
existing `"default"` agent entry is preserved. No clobbering risk.

## 2. Optional: _enroll_crew_members() — Phase 2b

If the PoC shows that `config.agents` alone does not cause the gateway to stamp
`KIROCREW_STUB_SESSION_TOKEN` on the spawned process, add a post-gateway-ready
enrollment step. This call is idempotent — `POST /api/agents` checks for an
existing entry before creating.

```python
def _enroll_crew_members(podman: PodmanClient, crew: dict) -> None:
    """Fully enroll each persona: allocates member_id + DM slot."""
    for name in ["ghost", "spectre", "banshee", "wraith", "reaper", "raven"]:
        try:
            _crew_api(crew, "POST", "/api/agents", json={
                "name": name,
                "kiro_agent": name,
                "memory_store": "default",
            })
        except Exception as e:
            logger.warning("Member enrollment for %s failed: %s", name, e)
```

Called after `_wait_for_gateway_ready()` in the launch path.

## 3. spawn_run tool usage

The `spawn_run` MCP tool (from `mcp_tools/spawn.py`):
```
spawn_run(task: str, agent: str = "", model: str = "", ...)
```

`agent` accepts a key from `config.agents`. Raven dispatching Banshee:
```
spawn_run(agent="banshee", task="REVIEW security <intent_id> <change> ...")
```

Attestation chain:
1. Raven's MCP server process has `KIROCREW_STUB_SESSION_TOKEN` in env
2. `spawn_run` → `mcp_core._post()` → `_session_token_header()` reads it
3. `/api/spawn` receives `X-Session-Token` + `X-Session-Key` + `X-Internal-Secret`
4. `session_key_is_attested()` returns True → spawn proceeds

## 4. Order template changes

### spec-driven-development.md
Remove all `curl -X POST .../api/spawn -H "X-Internal-Secret: ..."` dispatch
blocks. Replace with `spawn_run` tool call instructions:
```
Use the spawn_run tool: spawn_run(agent="spectre", task="SDD dispatch <intent_id> <change> ...")
```

Keep the intent-UUID idempotency pattern (maildeliver to Raven's mailbox before
dispatching) — that is unaffected.

### independent-review.md
Same pattern:
```
spawn_run(agent="wraith", task="REVIEW docs <change> ...")
spawn_run(agent="banshee", task="REVIEW security <change> ...")
```

## 5. Raven agent spec

`academy/agents/raven.json`:
- Add `"spawn_run"` to `allowedTools`
- Remove curl-based `/api/spawn` dispatch instructions from prompt
- Replace with `spawn_run` tool call instructions
- Keep all REST API references for status/steer/continue — those don't
  require attestation and still use `X-Internal-Secret` via curl fine

## 6. Captain dispatch of Raven — no change needed

The Captain dispatches Raven via the transport's external path. That path uses
cookie auth and works. The transport → Raven spawn is not the broken step.
The broken step is Raven → personas. No change to Captain order templates for
the dispatch mechanism itself.

## 7. What does NOT change

- Transport cookie-based auth (still correct for all lifecycle operations)
- Intent-UUID idempotency pattern in order templates
- Agent spec content (personality, capabilities) except `allowedTools` for raven
- The 5 other `academy/agents/` JSON files
- The attestation mechanism itself (no KiroCrew fork changes needed)
- Status/steer/continue REST calls from Raven (curl with X-Internal-Secret is
  fine for read operations — only spawn requires attestation)
