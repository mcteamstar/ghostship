# Findings: TRN-224 — Memory Retrieval Vector Similarity

**Verified:** 2026-10-11 · **Base image:** `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`
(digest `sha256:f4f4801898572175a1988e61a8696769821528860edceaf5ca253f8123a77009`)
**Verdict:** behaviour change / low impact — **no ghostship source change required.**
Operator note added; change ready for Ghost/Banshee review.

## 1. Migration + table-list probe (design D2.2)

**Live-image probe could not be run in this environment: no container runtime
(`podman`/`docker`) is installed on the implementer host.** This matches the
method already documented in `seed_kiro_db.py`'s header, which notes the base
image seeds no `data.sqlite3`, so the probe tuple is derived by static
extraction of kiro-cli 2.29.0's embedded migration SQL (migrations 000..005)
rather than by executing migrations in a live container.

The ghostship seed schema was probed directly (equivalent SQLite executescript):

| Probe | Result |
|---|---|
| `SELECT COUNT(*), MAX(version) FROM migrations` | **`(6, 5)`** — matches expected baseline |
| Table list | `['auth_kv', 'history', 'migrations', 'state']` |
| `memories` / `lessons` / embedding tables | **none** |

The `(6, 5)` result equals the baseline the seed header and
`tests/unit/test_seed_kiro_db.py` already pin (verified 2026-10-11 against
`0.9.0-insider.4`). **Migration count did not differ from `(6, 5)`**, so the
TRN-219 seed-schema deferral clause does not trigger — no seed edit in this
change.

## 2. No memory/embedding table in the pristine seed

Confirmed: the seed creates only the four gateway-infrastructure tables
(`auth_kv`, `history`, `migrations`, `state`) and no `memories`, `lessons`, or
embedding table. The vector-similarity memory subsystem is provisioned by the
gateway's own first-start migration, not by the ghostship seed — exactly as the
seed header comment states.

## 3. Enrollment / `_patch_crew_config()` against 0.9.0 base

`transport/lifecycle.py` line **1935** (the design doc's "~1895") writes
`"memory_store": "default"` inside the `full_overrides["agents"]` comprehension.
`"default"` is a store *selector* with no ordering/ranking assumption, so the
0.8.0→0.9.0 recency→vector-similarity switch is transparent to it. No
validation error is expected on this key under 0.9.0; `"default"` remains a
valid store id. **Line 1935 left unchanged; the comprehension is unchanged.**

## 4. `seed_kiro_db.py` needs no memory-table addition

Confirmed — schema stays `auth_kv` / `history` / `migrations` / `state`
(migrations 0–5). No memory-table addition required. Seed left unchanged.

## 5. Accumulated-memory re-embedding behaviour & startup latency

**Not directly observable in this environment** (no container runtime to boot a
persistent/general crew with pre-existing 0.8.0 memory rows). Per the upstream
behaviour (PR #3243, embed-at-write + rank-by-vector), the first start after
upgrade on a crew holding pre-0.9.0 memory rows may run a one-time re-embedding
pass to backfill vectors; this is a one-time startup cost that can be material
on large stores and does not recur on subsequent starts. Recorded as a risk in
the operator note rather than as a measured latency figure — the measurement
requires a live persistent crew on a Podman host and is a release-gate step for
whoever bumps/validates `KC_BASE_IMAGE` on such a host.

## 6. Ephemeral crew — no startup delay

The spec-ops crew starts fresh per project and holds **no** accumulated memory,
so there are no rows to re-embed and no memories to re-rank at first start → no
re-embedding pass, no startup delay, no behaviour shift. Confirmed by design:
ghostship pre-seeds no memory rows (finding 2), so a fresh crew's memory store
is empty until it accumulates rows during its own run.

## 7. Operator note

Added to `CHANGELOG.md` under the existing **"KiroCrew 0.8.0 → 0.9.0 upgrade"**
section (alongside the TRN-220 and TRN-221 entries), covering: the
recency→vector-similarity ranking change, task-behaviour shift on long-running
crews, the one-time re-embedding pass and its startup-latency risk on large
stores, and the fact that fresh/ephemeral crews are unaffected. This satisfies
every scenario in `specs/kc090-memory-vector-similarity/spec.md`.

## 8. Close-out

- No ghostship source change (seed + `memory_store` enrollment unchanged).
- Operator note shipped in `CHANGELOG.md`.
- Open item for the release-gate host (not this change): run the live Podman
  probe and measure the actual re-embedding startup latency on a persistent
  crew with a large accumulated-memory store before `KC_BASE_IMAGE` validation
  sign-off.
