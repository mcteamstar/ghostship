# TRN-186 Architecture Research: Crew Member Registration for Attested Persona Spawning

**Date:** 2026-10-02  
**Investigator:** Wraith  
**Sources examined:** `kirocrew/kiro_crew/mcp_tools/spawn.py`, `mcp_core.py` (lines 1420–1840), `session_token_sig.py`, `members.py`, `dashboard/session_control.py`, `config/sections.py`, `config/loader.py`, `transport/lifecycle.py`, `transport/captain.py`, `academy/agents/raven.json`, `academy/orders/spec-driven-development.md`

---

## 1. How `spawn_run` Achieves Attestation — The Exact Token Flow

### The full chain

```
spawn_run() [mcp_tools/spawn.py]
  └── mcp_core._resolve_session_key()           # resolves caller's session key
  └── mcp_core._post("/api/spawn", body)        # sends the spawn request
        └── headers = {
              **_session_token_header(),         # X-Session-Token
              **_caller_header(),                # X-Internal-Caller
              "X-Session-Key": resolved_key,    # session identity
            }
```

### `_session_token_header()` — exact token resolution (`session_token_sig.py` line 402)

```python
def session_token_header(token: str = "") -> dict[str, str]:
    from kiro_crew.mcp_gateway.claim import STUB_SESSION_TOKEN_ENV
    resolved = token or os.environ.get(STUB_SESSION_TOKEN_ENV, "")
    return {"X-Session-Token": resolved} if resolved else {}
```

`STUB_SESSION_TOKEN_ENV = "KIROCREW_STUB_SESSION_TOKEN"` (`mcp_gateway/claim.py` line 60).

The header is populated **from the process environment** — specifically the `KIROCREW_STUB_SESSION_TOKEN` env var injected into the MCP server process at session launch. This is set by `mcp_gateway/session_servers.py:attach_stub_session_token()`, which stamps the token on every managed MCP element before the process is spawned.

### What happens without a stub token

If `KIROCREW_STUB_SESSION_TOKEN` is absent from the environment, `_session_token_header()` returns `{}`. The `POST /api/spawn` request arrives with no `X-Session-Token`. The gateway's attestation check looks for either:
1. Unix socket kernel peer verification (`peer_verified=True`) — only available on the Unix domain socket, not loopback TCP
2. A valid signed `X-Session-Token` — absent when no token in env

Without either, the spawn fails with `member_identity_unavailable`.

### Why Raven's curl-based approach fails

Raven runs as a headless task dispatched via `kirocrew spawn`. Its MCP server process has `KIROCREW_STUB_SESSION_TOKEN` **only if** the gateway injected it at spawn time — which requires the session to be created through the gateway's session machinery with a `member_session_key`. When Raven is not a registered crew member, it is spawned as a generic agent with no member identity, so the stub token is never stamped on its environment, and its curl calls to `POST /api/spawn` with only `X-Internal-Secret` have no attestation token to send.

---

## 2. `config.agents` Registration — What It Enables and Whether It's Sufficient

### What a `config.agents` entry contains (`config/sections.py` line 3896)

```python
@dataclass
class KiroCrewAgentConfig:
    member_id: str = ""         # Immutable ID, assigned when member memory is created
    kiro_agent: str = ""        # Kiro agent name (spec file without .json)
    workspace: str = "default"
    memory_store: str = "default"
    model: str = ""
    session_control: bool = True   # Can open/drive other sessions
    member_dispatch: bool = True   # Can dispatch worker sessions
    crew_panel: bool = True
    # ...cost, timing fields...
```

### What registration in `config.agents` actually enables

A `config.agents` entry does **not** by itself create a member identity or stub session token. The config record is a *declaration* — it says "this persona is a crew member and here is its template." The following are separate enrollment steps that must happen:

1. **Member memory store creation**: A `member_id` must be allocated and a V2 memory store created. This happens when a member is first enrolled through the dashboard's `POST /api/agents` endpoint or `kirocrew agent create`.

2. **DM slot creation**: A pinned DM thread (`member-<slug>` slot key) must be created via the members endpoint. The slot key prefix `member-` is what `is_member_session_key()` tests for.

3. **Stub token stamping**: The stub session token is generated (`mint_stub_session_token()`) and attached to the MCP element environment at session spawn time by `mcp_gateway/session_servers.py:attach_stub_session_token()`. This only happens when the gateway creates a session with a valid `member_session_key`.

**Conclusion: `config.agents` registration alone is NOT sufficient.** A bare `config.agents` entry with no `member_id` produces what `crewmate_prune_migration.py` calls a "prune candidate" — a config row with no `member_id`. Without the `member_id` and a provisioned memory store, the gateway cannot resolve the member identity when spawning the persona, and `KIROCREW_STUB_SESSION_TOKEN` will not be stamped on its MCP environment.

The full enrollment path requires:
1. Writing the `config.agents` entry (what `_patch_crew_config` would do)
2. The gateway creating the member's V2 memory store and assigning `member_id`
3. The gateway creating the member's DM slot

On a fresh crew, steps 2–3 happen automatically the **first time** a member's DM thread is opened in the dashboard. There is no CLI command that pre-enrolls all steps in one shot without a dashboard interaction — but see section 5.

---

## 3. External `POST /api/spawn` with `parent_session="dashboard:member-raven"` — Does It Work?

### How `_member_caller()` works (`session_control.py` line 178)

```python
def _member_caller(state: DashboardState, caller_key: str) -> bool:
    from kiro_crew.members import DM_SLOT_KEY_PREFIX
    if caller_key.startswith(DM_SLOT_KEY_PREFIX):  # "member-"
        return True
    slot = state.get_slot(caller_key)
    if slot is None:
        return False
    return _store_is_member_owned(getattr(slot, "memory_store", "") or "")
```

A caller is recognized as a member if its session key starts with `member-` (DM slot) OR if it has a V2 member-owned memory store bound.

### Can the transport pass `parent_session="dashboard:member-raven"`?

**No, this does not grant attestation.** Setting `parent_session` in the spawn body only routes completion events back to that slot — it does not change how the calling session (the transport itself) is authenticated. The transport authenticates via the session cookie (`mc_token_5476`), which establishes the transport as a whitelisted internal caller. The `parent_session` field tells the gateway WHERE to deliver results, not WHO is making the request.

Even if the transport sends `parent_session="dashboard:member-raven"`, the spawned task does not run AS Raven's identity. It runs as the transport's generic caller context. The spawned Raven task would still have no `KIROCREW_STUB_SESSION_TOKEN`, because the member stub token is only stamped when the gateway creates a session for a **recognized member session key**, not when `parent_session` claims a member slot externally.

**However**, there is an important subtlety: the transport's cookie-based auth already passes the gateway's transport-internal authentication check (separate from spawn attestation). The transport currently succeeds in dispatching tasks this way. What fails is the **inner** spawn — when the Raven task itself tries to call `POST /api/spawn` to dispatch Spectre, Banshee, etc.

---

## 4. The Correct Architecture for Ghostship Attested Spawning

### Root cause, precisely stated

The current failure path:
```
Captain (cron) → transport → POST /api/spawn → Raven task [cookie auth: OK]
                                                    │
                                Raven task → POST /api/spawn → Spectre
                                             X-Internal-Secret only
                                             → member_identity_unavailable
```

The correct path requires Raven to run as an enrolled crew member whose session has `KIROCREW_STUB_SESSION_TOKEN` stamped on its MCP process environment. That happens automatically when:

1. Raven has a `config.agents` entry with a valid `member_id` and V2 memory store
2. The gateway spawns Raven's session using the `member_session_key` path (i.e., Raven is dispatched as a member DM session, not as a headless task)
3. Raven then calls `spawn_run(agent="spectre", task="...")` via the MCP tool — not curl — and `spawn_run` passes the stub token as `X-Session-Token`

### Two valid architectural paths

#### Path A: Full member registration (recommended, clean)

Register all 6 personas as crew members with `member_id` and V2 memory stores. The gateway then stamps stub tokens on all of them at session start. The dispatch chain becomes:

```
Captain (cron) → transport → POST /api/spawn (agent="raven") → Raven [as member DM session]
                                                                    │
                                                    Raven → spawn_run(agent="spectre")
                                                            → POST /api/spawn
                                                               X-Session-Token: <stub_token>
                                                               → ATTESTED: success
```

**Prerequisite:** The crew must have completed member enrollment for all 6 personas (gateway has assigned `member_id` and provisioned memory stores). The first time this happens requires the gateway to run, which means enrollment must happen at crew setup time, not just config patch time.

#### Path B: `spawn_run` MCP tool with no full member enrollment (incomplete — still breaks)

Even if `config.agents` entries are written but personas are not fully enrolled (`member_id` empty), `spawn_run` calls will fail because `KIROCREW_STUB_SESSION_TOKEN` requires a live member session identity. This path does not work.

---

## 5. What `kirocrew agent create` Does and Whether It Covers Enrollment

The `kirocrew agent create` CLI command (`cli_commands.py` line 1480) creates an agent spec JSON file in `~/.kiro/agents/` and writes the `config.agents` entry. **It also triggers member enrollment via the gateway's `POST /api/agents` HTTP endpoint**, which:
- Assigns a `member_id`
- Creates the V2 memory store
- Creates the DM slot

This is the correct enrollment path — but it requires the KiroCrew gateway to be running and reachable when called. Inside the crew container, this is available after the gateway has started.

**Implication for `_patch_crew_config`:** The existing approach patches `config.local.json` before the gateway has necessarily allocated `member_id`s. The solution is to run agent enrollment **after** the gateway is ready, via an additional setup step that calls the `POST /api/agents` endpoint for each persona using the crew's session cookie.

Alternatively: if the crew image is pre-seeded with enrolled member data (member directory structure under `~/.kiro/crew/members/`), the gateway can pick it up on first start without a separate enrollment call. This is analogous to how the `seed-kiro-db` mechanism works.

---

## 6. The Transport's Current Authentication Model

The transport does NOT use `X-Internal-Secret` for its own `POST /api/spawn` calls. From `transport/lifecycle.py`:

```python
def _crew_api(crew: dict, method: str, path: str, **kw: Any) -> Any:
    url = _crew_url(crew)
    r = _http.request(
        method, f"{url}{path}",
        headers={"Cookie": _crew_cookie(crew), "Origin": url},
        **kw,
    )
```

The transport uses a **session cookie** (`mc_token_{port}=<value>`), which is established via the gateway's web UI auth flow at crew start. This cookie authenticates the transport as a trusted web session — which is why the Captain → transport → Raven dispatch works. The `X-Internal-Secret` approach that Raven currently uses in its prompt is what fails.

However, the transport's own `POST /api/spawn` calls do **not** carry a `X-Session-Token` either. They pass the cookie, which maps to a web session, not a member session. The gateway accepts these because the transport is on an internal API path that the cookie's web session can reach — this is a different trust path than spawn attestation. The transport is not a member, and its spawns create headless tasks unless `parent_session` is set to route completions.

---

## 7. Exact Changes Needed (File by File)

### 7.1 `transport/lifecycle.py` — `_patch_crew_config`

**Change:** Add a `config.agents` section to `full_overrides` for all 6 personas. The `model` field should be left empty to inherit the global `agent.model`.

```python
full_overrides["agents"] = {
    "ghost":   {"kiro_agent": "ghost",   "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
    "spectre": {"kiro_agent": "spectre", "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
    "banshee": {"kiro_agent": "banshee", "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
    "wraith":  {"kiro_agent": "wraith",  "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
    "reaper":  {"kiro_agent": "reaper",  "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
    "raven":   {"kiro_agent": "raven",   "memory_store": "default", "model": "",
                "session_control": True, "member_dispatch": True},
}
```

**Critical caveat:** This adds the `config.agents` declaration but does NOT complete enrollment. A second step is needed.

**Open question (task 1.4 in tasks.md):** The design's open question 3 is confirmed as significant. Whether a headless dispatch of a `config.agents`-registered agent gets a stub token depends on whether `member_id` is populated. If it is empty, the gateway spawns the session without a member identity and no stub token is issued.

### 7.2 New step: Post-config enrollment call in lifecycle

After `_patch_crew_config` runs and the gateway becomes ready, a new step must enroll each persona via the gateway API. Two options:

**Option A — REST enrollment:** After the gateway is ready, call `POST /api/agents` for each persona via `_crew_api`:

```python
def _enroll_crew_members(podman: PodmanClient, crew: dict, crew_id: str) -> None:
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

This is the cleanest path. It must be called after `_wait_for_gateway_ready`.

**Option B — Pre-seeded member directories:** Pre-populate `~/.kiro/crew/members/<slug>/` for each persona in the container image or via a container script. This avoids the runtime enrollment call but is harder to maintain.

### 7.3 `academy/agents/raven.json` — Add `spawn_run` to `allowedTools`

```json
"allowedTools": ["read", "grep", "glob", "shell", "spawn_run"]
```

Also update the prompt's dispatch section. The line:
```
talk to the crew's own gateway directly over its REST API at localhost:5476 (POST /api/spawn ...), authenticating each request with the gateway's own local IPC credential at /home/kirocrew/.kiro/crew/.local_secret, passed as the X-Internal-Secret header.
```

Must become:
```
Use the spawn_run tool to dispatch named personas: spawn_run(agent="spectre", task="SDD dispatch <intent_id> <change> spectre ..."). Do not call /api/spawn directly via curl for persona dispatch — use spawn_run.
```

Keep the gateway REST API description for non-dispatch operations (`GET /api/spawn/{id}`, steer, continue) since those do not require attestation (they are reads or use the transport's auth context differently). The `X-Internal-Secret` approach for `POST /api/spawn` must be removed entirely for named persona spawning.

### 7.4 `academy/orders/spec-driven-development.md`

The template's dispatch section includes:
```
The gateway assigns the real spawn task ID inside `/api/spawn`, so do not invent or claim that ID before the call.
```

And:
```
calls the authenticated `/api/spawn`
```

These must be updated to describe `spawn_run` tool usage instead of direct REST calls. The intent-UUID idempotency pattern (writing pending markers to the raven mailbox before dispatching) is still valid — only the dispatch mechanism changes.

Replace all references to `curl -X POST .../api/spawn -H "X-Internal-Secret: ..."` with `spawn_run(agent="<persona>", task="SDD dispatch <intent_id> <change> <persona> ...")`.

### 7.5 `academy/orders/independent-review.md`

Same pattern: replace `POST /api/spawn` via curl with `spawn_run(agent="wraith"/"banshee", task="REVIEW ...")`.

### 7.6 `tests/unit/test_lifecycle.py`

Add tests asserting that `_patch_crew_config` produces `full_overrides` containing an `agents` key with all 6 persona entries, each having the correct `kiro_agent`, `memory_store`, `session_control`, and `member_dispatch` fields. Verify deep-merge does not overwrite the `default` agent entry.

---

## 8. Open Questions Resolved

### Q1: Does `config.agents` deep-merge preserve `default`?

**Yes.** `patch_crew_config.py` calls `_deep_merge(cfg, full_overrides)` which merges at the dict level. Adding `"agents": {"ghost": ..., "spectre": ...}` merges into the existing `"agents": {"default": ...}` without removing the `default` entry. Safe.

### Q2: Does `kiro_agent` accept a name or a path?

**A name only.** The loader in `config/loader.py` resolves `kiro_agent` against the agents directory (`kiro_agents_dir()`), looking for `<kiro_agent>.json`. The Ghostship agent specs are in `academy/agents/` and must be present in the container's agents directory at the path the gateway scans. The container already mounts or copies academy files, so the agent JSON names (`ghost`, `spectre`, etc.) will resolve correctly as long as those specs are in the agents directory.

### Q3: Must the Captain dispatch Raven via the DM path?

**Partially confirmed.** The Captain dispatches Raven via `_crew_api(..., "POST", "/api/spawn", json={"agent": "raven", ...})` using the transport's cookie auth. This creates a headless task, not a DM session. For the stub token to be stamped on Raven's MCP environment, the gateway must recognize the session as a member dispatch — which requires either:
- (a) The spawn request is routed through the member DM path, OR
- (b) The gateway's `SubagentManager` detects that `agent="raven"` matches a registered enrolled member and stamps the stub token on the spawned process automatically

**Option (b) is the clean path** and is what the design proposes. When a named `agent` in a spawn request matches an enrolled `config.agents` entry with a valid `member_id`, the gateway should (per KiroCrew's member-dispatch machinery) stamp `KIROCREW_STUB_SESSION_TOKEN` on the spawned MCP process. This is the behavior that needs to be verified with a PoC (task 1.2–1.3 in tasks.md).

If option (b) does not work (i.e. the stub token is only stamped for DM-slot sessions, not for headless-dispatched enrolled members), then the Captain's dispatch must change to create a DM slot: `_crew_api(..., "POST", "/api/spawn", json={"agent": "raven", "parent_session": "dashboard:member-raven", ...})` — but this would require the member DM slot to already exist.

**The PoC in task 1.2–1.3 is critical** before proceeding with the full implementation.

---

## 9. Summary: What Actually Needs to Change

| Component | Current state | Required change |
|-----------|--------------|-----------------|
| `transport/lifecycle.py: _patch_crew_config` | No `agents` key | Add all 6 persona entries to `full_overrides["agents"]` |
| `transport/lifecycle.py` (new step) | No enrollment | Add post-gateway-ready call to `POST /api/agents` for each persona |
| `academy/agents/raven.json` | `spawn_run` not in `allowedTools`, curl-based dispatch in prompt | Add `spawn_run` to `allowedTools`; replace curl dispatch with `spawn_run` tool call |
| `academy/orders/spec-driven-development.md` | Instructs `POST /api/spawn` via curl | Replace dispatch instructions with `spawn_run` tool usage |
| `academy/orders/independent-review.md` | Same | Same |
| `tests/unit/test_lifecycle.py` | No agent enrollment tests | Add tests for `_patch_crew_config` agents output and merge correctness |

### What does NOT change
- The transport's own cookie-based auth (still works, still correct)
- The intent-UUID idempotency pattern (still needed, mail-based)
- Agent spec content (personality, capabilities, tools — except `allowedTools` for Raven)
- The 6 agent JSON files in `academy/agents/` (other than `raven.json` above)
- The Captain cron dispatch of Raven via the transport (still works)

---

## 10. Confidence Assessment

**High confidence:**
- Token flow traced to source (verified in `session_token_sig.py`, `mcp_gateway/claim.py`, `spawn.py`)
- `config.agents` structure verified in `config/sections.py` and `loader.py`
- Transport cookie auth confirmed in `lifecycle.py` `_crew_api`
- `_member_caller()` logic fully traced in `session_control.py`
- `spawn_run` MCP tool correctly sends `X-Session-Token` via `_session_token_header()`

**Medium confidence — requires PoC:**
- Whether a headless-dispatched enrolled member automatically receives `KIROCREW_STUB_SESSION_TOKEN` without the DM slot being the session entry point (task 1.2–1.3)
- Whether the `POST /api/agents` enrollment call is idempotent on re-deployment

**Lower confidence — design calls to investigate:**
- The exact container script needed for `POST /api/agents` enrollment (needs `_crew_api` to be available, must run after gateway ready check)
