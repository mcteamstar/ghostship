# Tasks — TRN-219: Node 24 LTS crew image / base-image bump

## 1. Re-verify the migration schema (release gate)
- [ ] Pull `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` locally
- [ ] Run the schema-inspection command from `crews/_base/graduation/seed_kiro_db.py`'s header against `0.9.0-insider.4` and record the `(count, max_version)` tuple
- [ ] List the actual tables in the base image's `data.sqlite3` and diff against the seed's four tables (`auth_kv`, `history`, `migrations`, `state`)
- [ ] Record the kiro-cli version shipped in `0.9.0-insider.4` (for the header annotation)

## 2. Update `crews/_base/graduation/seed_kiro_db.py`
- [ ] If `(count, max_version)` ≠ `(6, 5)`: extend the `INSERT INTO migrations (version, migration_time) VALUES` block to versions `0..max_version` (one row each, `1700000000` placeholder time)
- [ ] If the table set changed: update the `conn.executescript` body — add/drop tables, adjust columns — while keeping `auth_kv (key TEXT PRIMARY KEY, value TEXT)` intact for `inject_auth.py`
- [ ] Update the ⚠️ header annotation: version string (`0.8.0 / kiro-cli 2.27.1` → 0.9.0 values), `Verified <date> against ...:0.9.0-insider.4: result (<count>, <max>)`, and the "Removed vs ..." provenance line
- [ ] If the schema is identical `(6, 5)`: update only the header annotation (verified tag + date + result), leave `executescript` and INSERT unchanged

## 3. Bump the base-image pin
- [ ] Edit `crews/_base/admission/Containerfile`: `ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (prefer the immutable `@sha256:f4f4801898...` digest)
- [ ] Edit `ghostship.conf` default `KC_BASE_IMAGE` to the identical value
- [ ] Edit `ghostship.conf.example` default `KC_BASE_IMAGE` to the identical value
- [ ] Confirm the Containerfile `ARG` default and the config default match exactly (plain `podman build` must equal an install build)

## 4. Verify spec-ops Node 24 layer (no change expected)
- [ ] Confirm `crews/spec-ops/Containerfile` still uses `setup_24.x` with `NODESOURCE_SETUP_SHA256="6e3d580f5bd7ccf2aa1e8df8d35c60d78e873c3ff8beb282c9bebd914904ad72"`
- [ ] Recompute the NodeSource script SHA-256 only if the `sha256sum -c -` step fails during build; update `NODESOURCE_SETUP_SHA256` if so

## 5. Build and validate
- [ ] Force a cache-less rebuild of the admission layer (base-image bump is a build-arg change; podman reuses layers on arg-only changes otherwise)
- [ ] Build the full chain: `base-admission` → `<comp>-mid` → `<comp>` (graduation)
- [ ] Launch a throwaway crew and confirm `inject_auth.py` succeeds (no `no such table: auth_kv`, auth insert complete)
- [ ] Confirm at least one agent authenticates and runs a trivial task end-to-end
- [ ] Confirm OpenSpec CLI still resolves inside the spec-ops image (`openspec --version`)

## 6. Record outcome
- [ ] Note the verified schema tuple and kiro-cli version in the commit message / change notes
- [ ] If schema differed and the seed was updated, document the delta for the next upgrade
