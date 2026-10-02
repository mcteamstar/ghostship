# TRN-186 Angle B: Member Enrollment — Does `config.agents` registration automatically create a member identity+memory store?

**Investigator:** Wraith  
**Date:** 2026-10-02  
**Related artifacts:** `openspec/changes/trn-186-crew-member-registration/`

---

## Executive summary

**No — `config.agents` registration alone does NOT automatically create a member identity or memory store.** Full enrollment (identity allocation + memory store provisioning + persistence) requires an explicit three-step call sequence that the ordinary config-patch path does NOT invoke. For TRN-186's proposed approach (writing entries via `config.local.json` in `_patch_crew_config`), the agents will exist in the roster but will have **no `member_id`** and will share the **default** memory store — which is intentional, but important to document.

---

## Finding 1: Where `config.agents` entries are loaded (`config/loader.py`)

**File:** `kiro_crew/config/loader.py` — `KiroCrewConfig._load_resolved()`

Agents entries in `config.json` / `config.local.json` are parsed at lines ~2285–2330 under:

```python
raw_agents = data.get("agents", {})
agents: dict[str, KiroCrewAgentConfig] = {}
if isinstance(raw_agents, dict):
    for name, entry in raw_agents.items():
        if isinstance(entry, dict):
            agents[name] = KiroCrewAgentConfig(
                member_id=entry.get("member_id", ""),
                kiro_agent=entry.get("kiro_agent", ""),
                workspace=entry.get("workspace", "default"),
                memory_store=entry.get("memory_store", "default"),
                ...
            )
```

**What this does:** Populates `KiroCrewConfig.agents` as a `dict[str, KiroCrewAgentConfig]` dataclass map. **Nothing more.** No filesystem writes, no memory store creation, no identity allocation. It is a pure read of stored JSON into Python objects.

A seeding migration (`MIGRATE_AGENTS`) creates a default `"default"` agent entry when `agents` is completely empty, but this also only touches the in-memory config and writes the config file — it does not provision a memory store.

---

## Finding 2: The full enrollment sequence (`members.py` + `memory_stores.py`)

Full member enrollment requires three explicit calls, only performed on the `kirocrew agent create` CLI path and the dashboard member-create endpoint:

### Step 1: `require_member_memory_creation(member)` — pre-flight check
**File:** `kiro_crew/member_memory_auth.py`

Guards against creating a member when the memory config is unreadable/degraded. A no-op if config is healthy.

### Step 2: `provision_member_memory(cfg, member)` — identity + store allocation
**File:** `kiro_crew/memory_stores.py`, line 1347

This is the critical step that does **not** happen on a plain config write:

1. Allocates a `member_id` (UUID-based, via `_allocate_member_id`)
2. Creates a unique named store directory: `member-<member_id[:32]>-<uuid>/` under `~/.kiro/crew/memory-stores/`
3. Calls `create_member_database()` to initialize the vector DB inside it
4. Creates `memory/preferences.md` and `memory/projects.md` scaffolding
5. Writes `agent.member_id` and `agent.memory_store` back onto the in-memory `KiroCrewAgentConfig`
6. Registers the new `MemoryStoreConfig(owner_member=member, owner_member_id=member_id, memory_version=2)` in `config.memory_stores`

**If this step is skipped:** the agent entry will have `member_id=""` and `memory_store="default"` — it shares the global memory store and has no private identity anchor.

### Step 3: `persist_member_config(cfg, member, create=True)` — atomic config write
**File:** `kiro_crew/memory_stores.py`, line 1464

Performs a locked `config.json` read-modify-write that:
- Writes the `agents[member]` record including `member_id` and the new `memory_store` name
- Writes the `memory_stores[<store>]` record with ownership metadata
- On create: also calls `crew_teams.release_for_create(name)` inside the lock to purge any stale team membership

**If this step is skipped:** the in-memory provisioning from Step 2 is never persisted to disk.

---

## Finding 3: CLI — `kirocrew agent create` subcommand

**File:** `kiro_crew/cli_commands.py`, `_handle_agent()`, line 1432

The CLI has three agent subcommands: `list`, `create`, `update`, `delete`.

`agent create` does run all three enrollment steps:
```python
require_member_memory_creation(args.name)
provision_member_memory(cfg, args.name)
persist_member_config(cfg, args.name, create=True)
```

Notably, the CLI **refuses** a non-default `memory_store` argument on create:
```python
if memory_store not in ("", DEFAULT_MEMORY_STORE):
    print("Error: members receive an empty member memory store automatically", ...)
    sys.exit(1)
```
This confirms that store allocation is always automatic — you cannot specify a custom store on create.

**No `enroll` or `add` subcommand exists.** The enrollment path is `agent create`.

---

## Finding 4: Dashboard member endpoint

**File:** `kiro_crew/dashboard/handlers/members.py`

The dashboard members handler provides the REST surface for member management. It calls through the same `provision_member_memory` + `persist_member_config` sequence as the CLI. Member DM threads are born exclusively from this handler with `mode="member"` slots — the generic slot-create endpoint deliberately excludes `"member"` from its allowed modes.

---

## Implications for TRN-186 design

The design doc proposes adding `config.agents` entries via `_patch_crew_config` writing to `config.local.json`, with `memory_store: "default"` for all six personas. Based on this investigation:

### What this approach WILL achieve:
- Personas appear in `config.agents` and are addressable by `spawn_run(agent="ghost", ...)`
- Each persona runs as a crew member → gets `member_session_key` → spawn attestation passes
- `KIROCREW_STUB_SESSION_TOKEN` is published to the MCP server env (since the session is member-keyed)
- The attestation fix for `/api/spawn` will work

### What this approach will NOT do:
- **No `member_id`** will be allocated (blank string in config)
- **No private memory store** will be created — all personas share the default store
- The `MemoryStoreConfig.memory_version` stays at 1 (legacy, shared pool)
- No `members/<slug>/` directory or activity log will exist until the first session runs

### Is this a problem?

For the TRN-186 goal (fixing spawn attestation), it is **not a problem**. The attestation mechanism keys off `is_member_session_key()` → the slot key prefix `member-<slug>`, which is set when the persona runs as a crew member regardless of whether a private memory store exists. The personas all use `memory_store: "default"` which is valid and expected for agents that share the global memory.

The missing `member_id` is also fine for this use case — `member_id` is only required for private per-member memory stores (V2). With `memory_store: "default"`, the system uses the shared pool and `member_id` is not consulted.

### One caveat: member slug derivation

`members.py` derives slugs via `slug_for_name(name)` → `slugify(name)`. For the persona names (`ghost`, `spectre`, etc.) these are already lowercase, slug-safe strings, so `slug_for_name("ghost")` → `"ghost"`. The `member_slug()` function first checks `agent.member_id` for an explicit stable slug; since `member_id=""` for the config.local.json approach, it falls back to `slug_for_name`, which is deterministic. **No issue here.**

---

## Source references

| Finding | File | Key line(s) |
|---------|------|-------------|
| Agents loaded from config | `kiro_crew/config/loader.py` | ~2285–2330 in `_load_resolved` |
| No provisioning on config load | `kiro_crew/config/loader.py` | MIGRATE_AGENTS creates entry, no store |
| Enrollment step 1 | `kiro_crew/member_memory_auth.py` | `require_member_memory_creation()` |
| Enrollment step 2 | `kiro_crew/memory_stores.py` | `provision_member_memory()` line 1347 |
| Enrollment step 3 | `kiro_crew/memory_stores.py` | `persist_member_config()` line 1464 |
| CLI agent create | `kiro_crew/cli_commands.py` | `_handle_agent()` line 1432 |
| Dashboard handler | `kiro_crew/dashboard/handlers/members.py` | POST /api/members |
| Member session key check | `kiro_crew/members.py` | `is_member_session_key()` |
