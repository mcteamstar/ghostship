# Proposal — TRN-219: Node 24 LTS crew image / base-image bump for KiroCrew 0.9.0

**Plane ticket:** TRN-219
**Change ID:** `trn-219-kc090-node24-crew-image`
**Author:** Spectre
**Context:** KiroCrew 0.9.0 preview upgrade (base image `0.8.0` → `0.9.0-insider.4`)
**Priority verdict (from research report):** **HARD BREAK** — conditional, silent-failure class.

## Why

KiroCrew 0.9.0 makes **Node 24 LTS a hard build requirement** (Node 22 floor) and
ships a new base image (`ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`). The crew
images must track that base image to run the 0.9.0 gateway.

The spec-ops image already installs Node 24 for OpenSpec's own benefit
(`crews/spec-ops/Containerfile`, `setup_24.x`), so the Node floor itself is not
the exposure. The real risk is the **kiro-cli migration schema** that
`crews/_base/graduation/seed_kiro_db.py` pre-seeds into the SQLite DB at build
time. That seed is pinned to the **0.8.0 / kiro-cli 2.27.1 schema (6 rows,
versions 0–5, `max_version 5`)** and was verified only against
`ghcr.io/kirodotdev/kirocrew:0.8.0`.

If `KC_BASE_IMAGE` is bumped to `0.9.0-insider.4` **without** re-verifying the
migration count/schema, and 0.9.0 added migrations, the seed will write the wrong
schema. The crew then **starts normally but auth injection fails silently** —
`inject_auth.py` hits `no such table: auth_kv`, or the auth insert misses required
columns — leaving agents unable to authenticate. This is a hard break that does
not surface at build time, only at first agent authentication.

This change makes bumping `KC_BASE_IMAGE` safe by binding it to a schema
re-verification step and updating the seed/annotations to match 0.9.0.

## What Changes

1. **Re-verify** the kiro-cli migration schema against
   `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` using the command already
   documented in `seed_kiro_db.py`'s header, before any image bump.
2. **Update `crews/_base/graduation/seed_kiro_db.py`** if the count/schema differs
   from `(6, 5)`: the `INSERT INTO migrations ... VALUES` block, the table
   `executescript`, and the ⚠️ header annotation (version string + verified-against
   tag + result tuple).
3. **Bump the `KC_BASE_IMAGE` default** in `crews/_base/admission/Containerfile`
   from `ghcr.io/kirodotdev/kirocrew:0.8.0` to the pinned `0.9.0-insider.4` (or its
   immutable digest), keeping it in sync with the `ghostship.conf` default.
4. **Confirm** `crews/spec-ops/Containerfile` Node 24 install
   (`setup_24.x`, `NODESOURCE_SETUP_SHA256`) remains valid — it already satisfies
   the Node 24 floor and needs no change unless the NodeSource script hash drifts.

## Affected ghostship files / functions

| File | What changes | Why |
|---|---|---|
| `crews/_base/graduation/seed_kiro_db.py` | `executescript` schema + `INSERT INTO migrations` rows + ⚠️ header annotation (version, verified tag, `(count, max)` tuple) | The seed must match the 0.9.0 base image's actual migration state or auth injection fails silently |
| `crews/_base/admission/Containerfile` | `ARG KC_BASE_IMAGE=` default pin | Base image must advance to the 0.9.0 gateway; default must stay in sync with `ghostship.conf` |
| `crews/spec-ops/Containerfile` | **Verify only** — `setup_24.x` + `NODESOURCE_SETUP_SHA256="6e3d58…"` already install Node 24 | Already correct for the Node 24 floor; the OpenSpec Node layer is independent of the gateway's internal Node |

## Non-goals

- Changing OpenSpec CLI pin (`@fission-ai/openspec@1.9.0`) — unrelated to the
  Node floor.
- Any change to the gateway's internal Node runtime — that ships inside the
  KiroCrew base image and is not under ghostship's control.
- The schema seed is build-time only; no runtime migration logic is added.
