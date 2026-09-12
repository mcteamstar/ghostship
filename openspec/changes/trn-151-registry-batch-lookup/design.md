## Context

`registry._find_batch_by_task_ids` is called by `pickup(task_ids=[...])` to locate the batch record so pickup can report aggregate status. It currently uses `set(provided) == set(recorded)`. The failure mode: a caller who lost one task ID from a partial dispatch can never resolve their batch.

## Goals / Non-Goals

**Goals:**
- Subset match: provided IDs ⊆ recorded batch IDs → match
- Keep exact match working (it's a special case of subset)
- Add tests for all match variants

**Non-Goals:**
- Superset match (caller passes more IDs than the batch) — ambiguous which batch is meant
- Fuzzy/partial matching on batch_id strings

## Decisions

**D1 — Subset semantics: `set(provided) <= set(recorded)`**

Replace `set(provided) == set(recorded)` with `set(provided) <= set(recorded)`. A subset of the batch's IDs is enough to identify it. Superset stays unmatched — if a caller has more IDs than any batch, something is wrong with their call.

**D2 — First-match wins**

If two batches somehow share task IDs (shouldn't happen, but UUID collisions are theoretically possible), the first match is returned. No change to existing tie-breaking logic.

## Risks / Trade-offs

- Subset matching could in theory return the wrong batch if task IDs from different batches were mixed by a caller. In practice UUIDs make this vanishingly unlikely, and the previous exact-match was stricter but silently broken in the real failure mode.
