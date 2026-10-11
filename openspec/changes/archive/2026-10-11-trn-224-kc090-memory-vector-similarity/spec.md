# Spec Delta: TRN-224 — Memory Retrieval Vector Similarity

**Change:** `trn-224-kc090-memory-vector-similarity`
**Plane ticket:** TRN-224
**Scope:** ghostship memory configuration + DB seed, under KiroCrew `0.9.0-insider.4`.

This is a **delta** spec: it records what changes in the memory subsystem that
ghostship interacts with, and what ghostship's interface/configuration looks
like after the 0.9.0 upgrade. Ghostship's own behaviour does **not** change;
the delta is the gateway behaviour ghostship now runs on top of, plus the
verification obligations that follow from it.

## Behaviour that changes (gateway, below ghostship)

### MODIFIED: Memory retrieval ranking
- **Was (0.8.0):** `memory_recall` and startup memory injection surfaced rows
  from the agent's `memory_store` in **recency order** (most-recent-first).
- **Now (0.9.0):** rows are embedded at write time; retrieval ranks by
  **cosine similarity** of the stored embedding vector against the query/turn
  embedding. Recency is no longer the primary ranking key.
- **Consequence for ghostship agents:** on a crew with accumulated memory, the
  set of memories injected into a given turn may differ from pre-upgrade. A
  recent-but-unrelated memory may drop out; an older-but-semantically-close
  memory may surface. Task output may therefore shift without any config or
  code change on ghostship's side.

### MODIFIED: Memory storage format
- Memory rows now carry a stored embedding vector written at insert time.
- On first start after upgrade, a crew with pre-existing memory rows (written
  under 0.8.0 without vectors) may undergo a **one-time re-embedding pass** to
  backfill vectors before similarity ranking is usable.

## Interface / configuration AFTER the change

### UNCHANGED: ghostship memory enrollment
Ghostship continues to enroll every deployed agent with the single memory key:

```json
"agents": {
  "<agent-stem>": {
    "kiro_agent": "<agent-stem>",
    "memory_store": "default",
    "session_control": true,
    "member_dispatch": true
  }
}
```

- `memory_store: "default"` remains a valid store identifier under 0.9.0.
- No new ghostship-written config key is required. In particular, ghostship
  does **not** need to set any embedding-model, re-embedding, or
  memory-ranking key — the gateway owns those defaults.

### UNCHANGED: DB seed schema
`seed_kiro_db.py` continues to seed only `auth_kv`, `history`, `migrations`
(versions 0–5, `(6, 5)`), and `state`. It introduces **no** `memories` /
`lessons` / embedding table. The memory tables remain gateway-migration-owned,
created on first start.

- **Verification obligation:** confirm against `0.9.0-insider.4` that the
  memory/embedding tables are still created by gateway migration (i.e. the
  migration `(COUNT, MAX(version))` probe result and the set of
  gateway-created tables), and that ghostship is **not** expected to
  pre-create any memory table in the seed.

## New / modified config keys

- **ghostship-owned keys:** none added, none modified. `memory_store:
  "default"` is retained verbatim.
- **Gateway-owned keys (informational, not written by ghostship):** the 0.9.0
  memory subsystem introduces embedding-at-write-time and vector ranking as
  internal defaults. Ghostship relies on these defaults and sets no override.

## Acceptance

- `memory_store: "default"` is accepted by `0.9.0-insider.4` and agents enroll
  with a working memory store.
- `seed_kiro_db.py` seed remains schema-correct (no missing memory table that
  the gateway expects ghostship to have pre-created).
- An operator note documents the retrieval-ordering change and the one-time
  re-embedding pass for long-running crews.
