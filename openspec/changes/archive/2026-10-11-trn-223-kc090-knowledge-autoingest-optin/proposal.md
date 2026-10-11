## Why

**Plane ticket:** TRN-223 — Knowledge auto-ingest opt-in (KiroCrew 0.9.0 upgrade).

KiroCrew 0.9.0 (PR #2448) makes the knowledge auto-ingest paths — the file-watcher,
the git commit hook, and clipboard capture — **opt-in**. Prior to this change they were
automatically enabled; after it they must be explicitly turned on under a `knowledge`
config section.

**Priority verdict (from the 0.9.0 research report):** **LOW IMPACT — no code change
required.** This is listed under "BEHAVIOUR CHANGES — should fix, crew still works",
but the source audit found ghostship was never relying on auto-ingest, so the
default-on → default-off flip does not change ghostship's effective configuration.

The audit (research report §3, TRN-223) read:

- `transport/lifecycle.py` — `_patch_crew_config()` and its `full_overrides` dict
  (lines ~1885–1965). The dict sets `stt.enabled=false`, `session.*`,
  `telemetry.beacon_enabled=false`, `auto_update=false`, `orchestrator.*`, and a
  generated `agents` block (`memory_store="default"`), but contains **no `knowledge`
  key**.
- `crews/_base/graduation/seed_kiro_db.py` — pre-seeds only `auth_kv`, `history`,
  `state`, and `migrations`. No knowledge tables or rows.
- `academy/agents/*.json` (`raven.json`, `spectre.json`, `ghost.json`, `banshee.json`,
  `wraith.json`, `reaper.json`) — contain no knowledge-related fields.
- `academy/steering/STANDING_ORDERS.md` — references a shared OpenSpec store and mail
  Maildir, but nothing that triggers knowledge auto-ingest.

The spec-ops crew is headless (no clipboard), its working directory is a transient git
worktree (not a persistently watched folder), and no `config.local.json` override ever
set `knowledge.auto_ingest=true`. So the pre-0.9.0 auto-ingest paths were never
exercised; disabling them by default is a no-op for ghostship.

This change therefore makes **no behavioural code change**. Its purpose is to (1) record
the verdict and the evidence so a future operator does not re-investigate, and (2) make
the "off by default" posture *explicit and intentional* rather than *incidental*, so a
later KiroCrew default flip in the other direction cannot silently enable ingest inside
a crew container.

## What Changes

### Documentation (required)

- Add a short "Knowledge auto-ingest" note to `docs/configuration.md` recording that
  ghostship does not enable auto-ingest and that under KiroCrew 0.9.0+ it is opt-in. An
  operator who wants crew-knowledge-from-commits in a mounted worktree must opt in
  explicitly.

### Config posture (DECIDED — Option B, no pin)

- No change to the `full_overrides` dict in `transport/lifecycle.py`. Task 2 verification
  against the pinned base image (`kiro_crew` 0.9.0rc4) found **no `knowledge.auto_ingest`
  key** in the real `KnowledgeConfig` schema — the ingest toggles are separate fields
  (`auto_ingest_artifacts`, `auto_add_documents`), each already defaulting to `false`.
  Pinning the assumed key would write an inert dead key, so **nothing is pinned** and the
  disabled posture relies on the verified upstream default. See `design.md` D1 (final =
  Option B).

### Verification (required)

- One source-level assertion test (`tests/unit/test_trn223_knowledge_autoingest.py`)
  confirming (a) ghostship's `full_overrides` contains no `knowledge` section / no implicit
  ingest enablement, and (b) the verified upstream ingest toggles still default to `false`
  — the Option-B tripwire that fails CI if a future upstream default flips.

## Non-Goals

- Enabling knowledge auto-ingest for any crew. This change does not turn ingest on.
- Seeding knowledge data in `seed_kiro_db.py`.
- Adding operator-facing `GA_*` env vars for knowledge configuration — ghostship exposes
  no knowledge knobs and this change introduces none.

## Affected ghostship files / functions

| File | Function / region | Change |
|---|---|---|
| `transport/lifecycle.py` | `_patch_crew_config()` → `full_overrides` dict (~L1885–1965) | No change — D1 resolved to Option B; the assumed `knowledge.auto_ingest` key does not exist upstream, so nothing is pinned |
| `docs/configuration.md` | new "Knowledge auto-ingest" note | Document opt-in posture under 0.9.0 (not pinned; relies on verified upstream default) |
| `transport/container_scripts/patch_crew_config.py` | `patch_config()` / `_deep_merge()` | No change — already deep-merges any new top-level section |
| `tests/unit/test_trn223_knowledge_autoingest.py` (new) | assertion on `full_overrides` + upstream defaults | Verify no implicit enablement; tripwire on upstream default flip |
