# Change: TRN-224 — Memory Retrieval Vector Similarity (0.9.0 verification)

**Plane ticket:** TRN-224
**Upgrade context:** ghostship → KiroCrew `0.9.0-insider.4`
**Priority verdict:** **BEHAVIOUR CHANGE / LOW IMPACT** — *no code change required; verification + operator note only.*

## Why

KiroCrew 0.9.0 changes how stored memories are ranked at retrieval time
(upstream PR #3243, "Memory: embed at write time; rank by stored vectors").

- **Before (0.8.0):** retrieval surfaced memories in **recency order**.
- **After (0.9.0):** memories are embedded at write time and ranked by
  **cosine similarity** of the stored embedding vectors against the current
  turn's embedding. This is also a **storage-format change** — rows now carry
  an embedding vector.

Ghostship touches memory in exactly two places, and neither is a code break:

1. `crews/_base/graduation/seed_kiro_db.py` pre-seeds the kiro-cli SQLite
   schema (`auth_kv`, `history`, `migrations`, `state`) but **seeds no memory
   rows and no `memories`/`lessons` table** — those tables are created by the
   gateway's own migration on first start, not by ghostship.
2. `transport/lifecycle.py` `_patch_crew_config()` enrolls every deployed
   agent with `"memory_store": "default"` (line 1895). This selects *which*
   store an agent uses; it seeds nothing and encodes no ordering assumption.

Because ghostship pre-seeds no memory and depends on no particular retrieval
ordering, a **fresh** spec-ops crew is unaffected: there are no memories to
rank until the crew accumulates them. The real-world impact is on
**long-running crews with accumulated memory** (e.g. a persistent general
crew), where post-upgrade task quality may shift as different memories get
injected, and the first turn after upgrade may trigger a **re-embedding pass**
over existing memory rows (a possible brief startup delay on large stores).

This change exists to make that assessment an **auditable artifact** and to
pin the exact code locations a future reviewer must re-check before bumping
`KC_BASE_IMAGE`, rather than to ship a behavioural code change ghostship does
not need.

## What Changes

- **No ghostship source change.** `seed_kiro_db.py` and the `memory_store`
  enrollment in `_patch_crew_config()` remain exactly as they are.
- **Verification artifact:** confirm the two memory touchpoints above still
  hold against `0.9.0-insider.4`, and confirm the seed schema (`(6, 5)`
  migrations) does not now include a memory/embedding table that ghostship
  would need to pre-create.
- **Operator note:** document the retrieval-ordering change and the one-time
  re-embedding pass so operators of long-running crews understand that
  post-upgrade task behaviour may differ and that a large memory store may
  incur a one-time startup delay.

## Affected ghostship files/functions

| File | Function / location | Role in this change |
|---|---|---|
| `crews/_base/graduation/seed_kiro_db.py` | top-level `conn.executescript(...)` schema (lines ~29–63) | Confirms ghostship seeds **no** memory table; verify 0.9.0 did not add one that must be pre-seeded. |
| `transport/lifecycle.py` | `_patch_crew_config()` → `full_overrides["agents"]` comprehension, `"memory_store": "default"` (line 1895) | The only ghostship-written memory config key; confirm `"default"` is still a valid store id under 0.9.0. |

## Priority / Risk

**Behaviour change only — not a hard break.** Ghostship does not seed memory
and does not depend on retrieval ordering, so this does not block the upgrade.
Risk is confined to long-running crews with accumulated memory (shifted task
quality + one-time re-embedding cost), not the ephemeral spec-ops crew.
