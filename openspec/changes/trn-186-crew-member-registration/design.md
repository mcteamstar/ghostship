# Design: TRN-186 Crew member registration

## 1. config.agents entries

`_patch_crew_config` will add this to `full_overrides` in `lifecycle.py`:

```python
"agents": {
    "ghost":   {"kiro_agent": "ghost",   "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
    "spectre": {"kiro_agent": "spectre", "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
    "banshee": {"kiro_agent": "banshee", "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
    "wraith":  {"kiro_agent": "wraith",  "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
    "reaper":  {"kiro_agent": "reaper",  "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
    "raven":   {"kiro_agent": "raven",   "memory_store": "default", "model": "", "session_control": True, "member_dispatch": True},
}
```

`kiro_agent` must match the filename in `/agents/` (without `.json`).
KiroCrew's config loader reads agent specs from that directory keyed by name.

## 2. spawn_run tool usage

The `spawn_run` MCP tool signature (from KiroCrew's mcp_core.py):
```
spawn_run(task: str, agent: str = "", model: str = "", crew: str = "", ...)
```

`agent` accepts a key from `config.agents`. So Raven dispatching Banshee becomes:
```
spawn_run(agent="banshee", task="REVIEW security <intent_id> <change> ...")
```

This is attested because:
1. Raven runs as a crew member → has `member_session_key`
2. `KIROCREW_STUB_SESSION_TOKEN` is published to Raven's MCP server env
3. `spawn_run` calls `/api/spawn` with `X-Session-Token` from env → passes `session_key_is_attested`

## 3. Order template changes

### spec-driven-development.md
Replace the dispatch section. Current pattern:
```bash
SECRET=$(cat /home/kirocrew/.kiro/crew/.local_secret)
curl -s -X POST http://localhost:5476/api/spawn \
  -H "X-Internal-Secret: $SECRET" \
  -H "Content-Type: application/json" \
  -d '{"task": "SDD dispatch <intent_id> ...", "agent": "spectre", "parent_session": "..."}'
```

New pattern — instruct Raven to use the `spawn_run` tool directly:
```
Use the spawn_run tool: spawn_run(agent="spectre", task="SDD dispatch <intent_id> <change> ...")
```

Remove all curl-based spawn instructions. Remove `X-Internal-Secret` references
from dispatch sections. Keep the intent marker mail pattern (that uses shell/maildeliver,
which is fine).

### independent-review.md
Same replacement: `spawn_run(agent="wraith", task="REVIEW docs ...")` etc.

## 4. Raven agent spec

Add `spawn_run` to `allowedTools` in `academy/agents/raven.json`:
```json
"allowedTools": ["read", "grep", "glob", "shell", "spawn_run"]
```

Update the prompt dispatch section: remove the curl-based `/api/spawn` instructions,
replace with `spawn_run` tool call instructions.

## 5. Captain dispatch of Raven

The Captain's standing order currently dispatches Raven via the transport's
external `POST /api/spawn`. That external dispatch still works (transport is
attested). No change needed here — the Captain → transport → Raven path is fine.
The fix is only needed for Raven → personas (the internal spawn chain).

## Open questions

1. Does `config.agents` in `config.local.json` merge with or replace the gateway's
   own `config.agents` entries? Need to verify deep-merge behaviour doesn't
   clobber the `default` agent entry.
2. Does `kiro_agent` in `config.agents` accept a path or just a name? Verify
   KiroCrew resolves it from the `/agents/` directory correctly.
3. Does Raven need to be dispatched as a member DM session (not headless) for
   `member_session_key` to be set? Or is registration in `config.agents` enough?
   The Wraith research says the member DM thread is what sets `member_session_key`.
   This may require the Captain to use the member DM path.

## Risk: open question 3

If Raven still needs to be dispatched via a member DM session (not headless),
the Captain order template also needs updating to use the DM path. This is the
most uncertain part. Recommend testing with a minimal proof-of-concept first:
register one persona as a crew member and test if a headless dispatch of it
gets an attested session.
