# Design: TRN-224 — Memory Retrieval Vector Similarity

**Change:** `trn-224-kc090-memory-vector-similarity`
**Plane ticket:** TRN-224
**Grounded in:** `transport/lifecycle.py` (`_patch_crew_config`),
`crews/_base/graduation/seed_kiro_db.py` (schema seed).

## D1. The two memory touchpoints in ghostship

Ghostship interacts with KiroCrew memory in exactly two code locations. Both
were read directly; neither requires a behavioural code change for 0.9.0.

### D1.1 Agent enrollment — `transport/lifecycle.py:1895`

Inside `_patch_crew_config()`, the `full_overrides` structure builds the
`agents` section with a dict comprehension that enrolls every deployed agent
file. The memory key is written here:

```python
# transport/lifecycle.py  (full_overrides["agents"], ~line 1888–1897)
"agents": {
    af.stem: {
        "kiro_agent": af.stem,
        "memory_store": "default",      # ← line 1895: the only memory key ghostship writes
        "session_control": True,
        "member_dispatch": True,
    }
    for af in Path("/agents").glob("*.json")
    if _manifest_selects(manifest_agents, af.name)
},
```

This dict is base64-encoded (`overrides_b64`) and handed to
`patch_crew_config.py`, which deep-merges it into `config.local.json`. The key
`"memory_store": "default"` is a **store selector** — it names which memory
store the agent reads/writes. It carries **no ordering or ranking assumption**,
so the 0.8.0→0.9.0 switch from recency to vector similarity is transparent to
this code: the string `"default"` is still a valid store id.

**Design decision:** leave line 1895 unchanged. There is no ghostship-owned
knob for ranking mode; ranking is a gateway-internal default. Adding one would
be inventing configuration the gateway does not expose through this path.

### D1.2 DB seed — `crews/_base/graduation/seed_kiro_db.py`

The seed script bakes the kiro-cli SQLite DB into the crew image at build time.
Its `conn.executescript(...)` block (lines ~29–63) creates **only** these
tables:

```python
CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE history (... 11 columns ...);
CREATE TABLE migrations (id INTEGER PRIMARY KEY, version INTEGER NOT NULL,
                         migration_time INTEGER NOT NULL);
CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO migrations (version, migration_time) VALUES
    (0, 1700000000), (1, ...), (2, ...), (3, ...), (4, ...), (5, 1700000000);
```

There is **no** `memories`, `lessons`, or embedding table in the seed. The
header comment is explicit that the memory/conversation tables are gateway-
owned and that this seed deliberately covers only the four tables above
("Removed vs 0.5.0 seed: conversations, conversations_v2 ..."). The gateway's
own migration creates and (under 0.9.0) extends the memory tables on first
start.

**Design decision:** leave the seed unchanged. The vector-ranking change lives
in gateway-created memory tables that this seed never touches. Pre-seeding an
embedding column here would duplicate — and risk drifting from — the gateway's
own migration schema, which is exactly the failure mode the seed's header
comment warns against for the auth/migration tables.

## D2. Verification steps (the actual work of this change)

The change is a verification artifact. The implementer runs these against
`0.9.0-insider.4` before `KC_BASE_IMAGE` is bumped.

### D2.1 Confirm `memory_store: "default"` still valid
Deploy a crew (or dry-run `_patch_crew_config`) against the 0.9.0 base image
and confirm agents enroll without a config-validation error on the
`memory_store` key. If 0.9.0 renamed `"default"` or introduced a required
companion key, line 1895 would need updating — expected: no change.

### D2.2 Confirm memory tables remain gateway-migration-owned
Reuse the migration probe already documented in `seed_kiro_db.py`'s header, and
additionally dump the table list, to confirm 0.9.0 does not expect ghostship to
pre-create a memory/embedding table:

```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
   print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone()); \
   print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"
```

- If the migration count/`MAX(version)` differs from `(6, 5)`, that is the
  TRN-219 seed-schema concern (handled by that change) — note it and defer the
  seed bump to TRN-219's path.
- If a memory/embedding table appears only after the gateway's own first-start
  migration (not in the pristine image), ghostship's seed is correct as-is.

### D2.3 Observe one-time re-embedding on an accumulated-memory crew
On a crew that already holds 0.8.0-era memory rows, start it on
`0.9.0-insider.4` and watch the first startup for a re-embedding pass. Record
whether it adds material startup latency. The ephemeral spec-ops crew starts
fresh per project and holds no accumulated memory, so this applies only to a
persistent/general crew.

## D3. Operator note (documentation deliverable)

Add a short operator-facing note (release/upgrade notes for the 0.9.0 bump)
stating:

> Memory retrieval in 0.9.0 ranks by vector similarity rather than recency.
> On a long-running crew with accumulated memory, the memories injected into a
> turn may differ post-upgrade, so task behaviour may shift. The first start
> after upgrade may run a one-time re-embedding pass over existing memory rows,
> which can briefly delay startup on large stores. Fresh/ephemeral crews
> (e.g. spec-ops) are unaffected.

## D4. Out of scope

- No change to retrieval ranking logic (gateway-owned).
- No new ghostship config key.
- No seed-schema edit for memory (seed bump, if any, is TRN-219's concern and
  is driven by the migration-count probe, not by this change).
