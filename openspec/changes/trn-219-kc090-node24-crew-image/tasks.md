# Tasks — TRN-219: Node 24 LTS crew image / base-image bump

> **Implementation note (Ghost, 2026-10-11):** Tasks §1 and §5, and the
> schema-dependent half of §2 and §6, are **release-gate verification steps that
> require a live Podman host plus a network pull of
> `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`**. Neither Podman nor registry
> access exists in the build sandbox this was implemented in, so those steps
> are left **unchecked and marked BLOCKED** rather than guessed — fabricating a
> `(count, max_version)` tuple or kiro-cli version string is exactly the
> silent auth-injection regression this change guards against. The deterministic
> code/config edits (the pin bump and its sync points) are complete and
> committed. The seed `executescript`/`INSERT` body is intentionally left
> unchanged pending the §1 inspection result (design.md §2.1 default branch).

## 1. Re-verify the migration schema (release gate) — BLOCKED (needs Podman + registry pull)
- [ ] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` locally
- [ ] Run the schema-inspection command from `crews/_base/graduation/seed_kiro_db.py`'s header against `0.9.0-insider.4` and record the `(count, max_version)` tuple
- [ ] List the actual tables in the base image's `data.sqlite3` and diff against the seed's four tables (`auth_kv`, `history`, `migrations`, `state`)
- [ ] Record the kiro-cli version shipped in `0.9.0-insider.4` (for the header annotation)

## 2. Update `crews/_base/graduation/seed_kiro_db.py`
- [ ] If `(count, max_version)` ≠ `(6, 5)`: extend the `INSERT INTO migrations (version, migration_time) VALUES` block to versions `0..max_version` (one row each, `1700000000` placeholder time) — BLOCKED on §1 result
- [ ] If the table set changed: update the `conn.executescript` body — add/drop tables, adjust columns — while keeping `auth_kv (key TEXT PRIMARY KEY, value TEXT)` intact for `inject_auth.py` — BLOCKED on §1 result
- [ ] Update the ⚠️ header annotation: version string (`0.8.0 / kiro-cli 2.27.1` → 0.9.0 values), `Verified <date> against ...:0.9.0-insider.4: result (<count>, <max>)`, and the "Removed vs ..." provenance line — BLOCKED on §1 result (needs verified tuple + kiro-cli version)
- [ ] If the schema is identical `(6, 5)`: update only the header annotation (verified tag + date + result), leave `executescript` and INSERT unchanged — BLOCKED on §1 result

## 3. Bump the base-image pin
- [x] Edit `crews/_base/admission/Containerfile`: `ARG KC_BASE_IMAGE=` to the immutable `@sha256:f4f4801898...` digest of `0.9.0-insider.4` (digest form preferred per design.md §3)
- [x] Edit the config default `KC_BASE_IMAGE` to the identical value (`transport/config.py` `Config.from_env`; `ghostship.conf` is not present in-repo — the authoritative default lives in `config.py`)
- [x] Edit `config/ghostship.conf.example` default `KC_BASE_IMAGE` to the identical value
- [x] Confirm the Containerfile `ARG` default and the config default match exactly (plain `podman build` must equal an install build) — both set to the same digest ref

## 4. Verify spec-ops Node 24 layer (no change expected)
- [x] Confirm `crews/spec-ops/Containerfile` still uses `setup_24.x` with `NODESOURCE_SETUP_SHA256="6e3d580f5bd7ccf2aa1e8df8d35c60d78e873c3ff8beb282c9bebd914904ad72"` — confirmed present and unchanged
- [x] Recompute the NodeSource script SHA-256 only if the `sha256sum -c -` step fails during build — not applicable until a build runs (§5); no change made

## 5. Build and validate — BLOCKED (needs Podman + registry pull)
- [ ] Force a cache-less rebuild of the admission layer (base-image bump is a build-arg change; podman reuses layers on arg-only changes otherwise)
- [ ] Build the full chain: `base-admission` → `<comp>-mid` → `<comp>` (graduation)
- [ ] Launch a throwaway crew and confirm `inject_auth.py` succeeds (no `no such table: auth_kv`, auth insert complete)
- [ ] Confirm at least one agent authenticates and runs a trivial task end-to-end
- [ ] Confirm OpenSpec CLI still resolves inside the spec-ops image (`openspec --version`)

## 6. Record outcome
- [ ] Note the verified schema tuple and kiro-cli version in the commit message / change notes — BLOCKED on §1 result
- [x] If schema differed and the seed was updated, document the delta for the next upgrade — N/A until §1 runs; the pin-bump commit documents what was and was not done

## Done in this pass (deterministic, no build host required)
- Base-image pin bumped `0.8.0` → `0.9.0-insider.4` (immutable digest) across all
  three authoritative locations: `crews/_base/admission/Containerfile` ARG,
  `transport/config.py` `kc_base_image` default, and
  `config/ghostship.conf.example`.
- `docs/configuration.md` `KC_BASE_IMAGE` reference updated to the new default.
- `tests/unit/test_seed_kiro_db.py::_parse_base_image` extended to recognise the
  `@sha256:<digest>` reference form in addition to `:<tag>`, so the slow CI guard
  resolves the new digest pin correctly.
- spec-ops Node 24 layer verified unchanged (§4).

## Remaining before release (requires a Podman build host)
1. Run §1 inspection against `0.9.0-insider.4`; record `(count, max_version)` and
   the kiro-cli version.
2. Apply §2 per the result: header-only if `(6, 5)` and tables unchanged;
   otherwise extend the `INSERT`/`executescript` and update
   `tests/unit/test_seed_kiro_db.py` `EXPECTED_COUNT`/`EXPECTED_MAX_VERSION`.
3. Run §5 build + end-to-end auth validation.
4. Record the verified tuple in §6 / the release commit.
