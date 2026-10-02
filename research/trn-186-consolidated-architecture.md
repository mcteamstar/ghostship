# TRN-186 Consolidated Architecture Report: Ghostship Crew Member Registration

**Date:** 2026-10-02  
**Synthesized by:** Raven  
**Sources:**
- `repo/research/trn-186-crew-member-architecture.md` (broad Wraith investigation)
- `repo/research/trn-186-angle-a-token-flow.md` (token flow)
- `repo/research/trn-186-angle-b-member-enrollment.md` (member enrollment)
- `repo/research/trn-186-angle-c-external-spawn.md` (external spawn + slot routing)
- `repo/research/trn-186-angle-d-transport-gap.md` (transport attestation gap)

---

## 1. The Exact Attestation Token Flow End-to-End

### Full chain for an attested MCP spawn (what works today for in-container agents)

```
KiroCrew gateway starts
  → attach_stub_session_token() stamps KIROCREW_STUB_SESSION_TOKEN
    into the MCP server process element env array
  → MCP server process (kirocrew-core) inherits the env var

Agent calls spawn_run(agent="spectre", task="...")
  → mcp_tools/spawn.py
  → _resolve_session_key() — resolves caller session key:
       1. current_caller().session_key  (gateway-injected per-call)
       2. session_key_from_env_token()  (reads KIROCREW_STUB_SESSION_TOKEN,
          verifies HMAC-signed mapping file, returns session key)
       3. KIROCREW_SESSION_KEY env var   (fallback, stale after rekey)
  → _post("/api/spawn", body, headers={
        "X-Session-Token": <token from KIROCREW_STUB_SESSION_TOKEN>,
        "X-Internal-Secret": <gateway local secret>,
        "X-Session-Key": <resolved session key>
    })
  → gateway /api/spawn handler:
       internal_auth = True  (X-Internal-Secret present)
       member_request_scope():
         session_key_is_attested() → AF/UNIX peer credential check
         returns MemberScope(session=<key>, verified=True, store=<store>)
       attested → spawn proceeds with member execution context
       KIROCREW_STUB_SESSION_TOKEN stamped on spawned process env
```

### Why the current Ghostship Raven dispatch fails

```
transport  →  POST /api/spawn
               Cookie: mc_token_5476=<session_cookie>
               Origin: http://gs-<id>:5476
               (no X-Internal-Secret, no X-Session-Key, no X-Session-Token)

  → gateway: cookie-auth path (not internal_auth)
  → no member_session_key derived
  → spawned Raven session: no KIROCREW_STUB_SESSION_TOKEN stamped

Raven task attempts to dispatch Spectre:
  → POST /api/spawn
    X-Internal-Secret: <read from .local_secret>
    (no X-Session-Token — env var was never set)
    (no X-Session-Key  — token-based resolution fails with empty token)

  → gateway: internal_auth = True, but session resolution:
       session_key_from_env_token() → KIROCREW_STUB_SESSION_TOKEN absent → ""
       KIROCREW_SESSION_KEY absent → ""
       session = "" → MemberScope(session=None, verified=True, store=None)
       claimed_session (parent_session) = "dashboard:member-spectre" ≠ None
       → 409 member_identity_unavailable
```

**Root cause:** The transport's cookie-auth path does not cause the gateway to stamp `KIROCREW_STUB_SESSION_TOKEN` on the spawned MCP process environment. Without the token, all downstream spawn attempts by Raven fail attestation.

---

## 2. Is `config.agents` + Enrollment the Right Path?

**Yes — but enrollment has two distinct requirements:**

### What `config.agents` alone does

Adding entries to `config.local.json` under `"agents"` populates the `KiroCrewConfig.agents` roster. It is a declaration only — no `member_id` is allocated, no memory store provisioned, no stub token issued.

### What full enrollment adds

Full enrollment (via `kirocrew agent create` or `POST /api/agents`) additionally:
1. Allocates a `member_id` (UUID)
2. Creates a private V2 memory store under `~/.kiro/crew/memory-stores/`
3. Creates the member DM slot key (`member-<slug>`)
4. Persists `member_id` and `memory_store` name back to `config.json`

### Is full enrollment required for TRN-186?

**No — for spawn attestation only, `config.agents` with `memory_store: "default"` is sufficient**, provided the gateway recognizes a named `agent` in a spawn request as a registered member and stamps the stub token. This is because:

- `is_member_session_key()` keys off the slot key prefix `member-`, not `member_id`
- Personas using `memory_store: "default"` are valid crew members sharing the global store
- The `member_id` field is only required for per-persona private memory (V2); it can be empty for the shared-store use case

**Critical open question (from angle B):** Whether a headless-dispatched spawn with `agent="raven"` (no DM slot, just config.agents entry) causes the gateway's `SubagentManager` to stamp `KIROCREW_STUB_SESSION_TOKEN` on the spawned MCP process — even without a DM-slot session key. This must be validated with a PoC (see section 4). If it does not stamp the token, the Captain's dispatch of Raven must use the DM slot path.

---

## 3. The Correct Way for Ghostship to Achieve Attested Named-Persona Spawning

### Recommended architecture (two-phase)

**Phase 1 — Config registration (at crew setup time, via `_patch_crew_config`):**

Add all 6 persona entries to `full_overrides["agents"]`:

```python
full_overrides["agents"] = {
    "ghost":   {"kiro_agent": "ghost",   "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "spectre": {"kiro_agent": "spectre", "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "banshee": {"kiro_agent": "banshee", "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "wraith":  {"kiro_agent": "wraith",  "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "reaper":  {"kiro_agent": "reaper",  "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "raven":   {"kiro_agent": "raven",   "memory_store": "default",
                "session_control": True, "member_dispatch": True},
}
```

This is a deep-merge safe — existing `"default"` agent entry is preserved.

**Phase 2 — Runtime dispatch change (in `raven.json` allowedTools + prompt):**

Raven must dispatch personas using the `spawn_run` MCP tool, NOT via curl to `/api/spawn`. The `spawn_run` tool automatically carries `X-Session-Token` + `X-Session-Key` + `X-Internal-Secret` through the MCP layer, where the headers are set and the token is available.

```json
// raven.json allowedTools — add spawn_run
"allowedTools": ["read", "grep", "glob", "shell", "spawn_run"]
```

Replace in Raven's prompt:
```
// REMOVE:
talk to the crew's own gateway directly over its REST API at localhost:5476 
(POST /api/spawn ...), authenticating with X-Internal-Secret header.

// ADD:
Use spawn_run(agent="<persona>", task="...") to dispatch named personas.
Keep the gateway REST API (GET /api/spawn/{id}, steer, continue) for 
status and control operations — those do not require attestation.
```

**Why spawn_run works where curl does not:** `spawn_run` is an MCP tool call — it goes through `mcp_tools/spawn.py` which reads `KIROCREW_STUB_SESSION_TOKEN` from the process env (stamped there at session start) and sends it as `X-Session-Token`. Curl cannot do this because the env var is only present in the MCP server process, and curl started by the shell tool inherits it — but a raw curl POST would need to construct `X-Session-Key` as well, which requires the HMAC-verified mapping file lookup. The MCP tool handles all of this transparently.

**If Phase 1 alone (config.agents) does not cause stub token stamping:**

A fallback Phase 2b may be needed: add a post-gateway-ready enrollment step that calls `POST /api/agents` for each persona to fully enroll them (allocate `member_id`, create DM slot). This ensures the gateway recognizes the session as a member dispatch and stamps the token. This requires a PoC to determine necessity.

---

## 4. File-by-File Changes Needed

### 4.1 `transport/lifecycle.py` — `_patch_crew_config`

**Change:** Add `agents` key to `full_overrides`:

```python
full_overrides["agents"] = {
    "ghost":   {"kiro_agent": "ghost",   "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "spectre": {"kiro_agent": "spectre", "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "banshee": {"kiro_agent": "banshee", "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "wraith":  {"kiro_agent": "wraith",  "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "reaper":  {"kiro_agent": "reaper",  "memory_store": "default",
                "session_control": True, "member_dispatch": True},
    "raven":   {"kiro_agent": "raven",   "memory_store": "default",
                "session_control": True, "member_dispatch": True},
}
```

**Optionally add** (if Phase 2b is needed after PoC): a `_enroll_crew_members()` function called after `_wait_for_gateway_ready()`:

```python
def _enroll_crew_members(podman: PodmanClient, crew: dict, crew_id: str) -> None:
    """POST /api/agents for each persona to fully enroll with member_id."""
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

This call is idempotent — `POST /api/agents` checks for an existing entry before creating.

### 4.2 `academy/agents/raven.json` — allowedTools + prompt

**Change 1 — allowedTools:** Add `"spawn_run"` to the array.

**Change 2 — prompt dispatch section:** Replace the direct curl-based spawn instructions with `spawn_run` tool instructions. Keep all REST API references for steer/continue/status (those do not require attestation). Remove the instruction to use `X-Internal-Secret` for `POST /api/spawn` persona dispatch.

### 4.3 `academy/orders/spec-driven-development.md`

**Change:** Replace all `curl -X POST .../api/spawn -H "X-Internal-Secret: ..."` persona dispatch references with:

```
Use spawn_run(agent="<persona>", task="SDD dispatch <intent_id> <change> <persona> ...")
```

The intent-UUID idempotency pattern (writing pending markers to the Raven mailbox before calling spawn_run) is still valid and should be preserved. Only the dispatch mechanism changes.

### 4.4 `academy/orders/independent-review.md`

**Change:** Same pattern — replace `POST /api/spawn` via curl with `spawn_run(agent="wraith"/"banshee", task="REVIEW ...")`.

### 4.5 `tests/unit/test_lifecycle.py`

**New tests to add:**
- `test_patch_crew_config_produces_agents_key()` — verify all 6 persona entries present in `full_overrides["agents"]`
- `test_patch_crew_config_deep_merge_preserves_default()` — verify `agents.default` entry is not overwritten
- `test_patch_crew_config_agents_have_correct_fields()` — verify each entry has `kiro_agent`, `memory_store`, `session_control`, `member_dispatch` with correct values

---

## 5. What Does NOT Change

- The transport's cookie-based auth (still correct for lifecycle operations)
- The intent-UUID idempotency pattern (still needed, still mail-based)
- Agent spec content (personality, capabilities) — except `allowedTools` for `raven.json`
- The Captain cron dispatching Raven via the transport (still works for the initial dispatch)
- The 5 other agent JSON files in `academy/agents/` (no changes)
- The attestation mechanism itself (no KiroCrew changes needed)

---

## 6. Key Confirmed Facts

| Question | Answer | Confidence |
|----------|--------|------------|
| Does `config.agents` alone create a member identity? | No — config write only, no member_id | High |
| Does `KIROCREW_STUB_SESSION_TOKEN` inherit to shell subprocesses of MCP servers? | Yes (standard env inheritance), stripped by stub.py for 3rd-party backends | High |
| Can X-Internal-Secret alone route a spawn into a member DM slot? | No — 409 member_identity_unavailable | High |
| Does the transport carry X-Session-Key or X-Session-Token? | No — Cookie + Origin only | High |
| What changed in 0.6.0 that matters? | Text-based credential gate removed; bind masks are sole fence | High |
| Can spawn_run MCP tool carry attestation headers? | Yes — reads KIROCREW_STUB_SESSION_TOKEN from process env automatically | High |
| Does config.agents entry (no member_id) suffice for stub token stamping? | Unknown — requires PoC | Medium |
| Is a POST /api/agents enrollment step needed? | Possibly — if config-only doesn't trigger stub token stamping | Medium |

---

## 7. Recommended Implementation Sequence

1. **Add config.agents entries** in `_patch_crew_config` (lifecycle.py)
2. **Add spawn_run to raven.json allowedTools** and update prompt  
3. **Update sdd.md and independent-review.md** dispatch instructions
4. **Run PoC** — deploy a crew with config.agents entries (no member_id), have Raven dispatch a Spectre via spawn_run; confirm KIROCREW_STUB_SESSION_TOKEN is present in Raven's MCP env
5. **If PoC passes:** proceed to implementation + tests
6. **If PoC fails (stub token absent):** add `_enroll_crew_members()` step after gateway ready, then retry PoC
7. **Add tests** for _patch_crew_config agents output

The PoC in step 4 is the critical gate — it determines whether Phase 2b (enrollment step) is required. All other changes are well-understood and low-risk.
