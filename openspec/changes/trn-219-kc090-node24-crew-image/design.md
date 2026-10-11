# Design — TRN-219: Node 24 LTS crew image / base-image bump

Implementation design grounded in the actual ghostship source read for this change:
`crews/spec-ops/Containerfile`, `crews/_base/admission/Containerfile`,
`crews/_base/graduation/seed_kiro_db.py`.

## 1. The actual exposure is the seed, not the Node floor

`crews/spec-ops/Containerfile` already installs Node 24 (lines 15–27):

```dockerfile
ARG NODESOURCE_SETUP_SHA256="6e3d580f5bd7ccf2aa1e8df8d35c60d78e873c3ff8beb282c9bebd914904ad72"
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_24.x -o /tmp/nodesource_setup.sh && \
    echo "${NODESOURCE_SETUP_SHA256}  /tmp/nodesource_setup.sh" | sha256sum -c - && \
    bash /tmp/nodesource_setup.sh && \
    ...
    apt-get install -y -qq --no-install-recommends nodejs && \
```

This layer sits on top of `localhost/base-admission:latest` and exists only so the
OpenSpec CLI (`npm install -g @fission-ai/openspec@1.9.0`) has a Node runtime. It is
**independent of the gateway's internal Node**, which ships inside the KiroCrew base
image. So the "Node 24 floor" headline is already satisfied — no edit needed here.

The real hard break lives one layer down, in the DB seed baked by the graduation
layer.

## 2. seed_kiro_db.py — the schema is pinned to 0.8.0

`crews/_base/graduation/seed_kiro_db.py` runs at build time and writes
`/home/kirocrew/.local/share/kiro-cli/data.sqlite3` so transport only INSERTs
`auth_kv` rows at launch. The header docstring pins the schema explicitly:

```
⚠️  Migration schema for KiroCrew 0.8.0 / kiro-cli 2.27.1 (6 rows, versions 0-5, max_version 5).
    Verified 2026-10-09 against ghcr.io/kirodotdev/kirocrew:0.8.0: result (6, 5).
```

The body seeds exactly four tables and six migration rows:

```python
conn.executescript("""
CREATE TABLE auth_kv ( key TEXT PRIMARY KEY, value TEXT );
CREATE TABLE history ( id INTEGER PRIMARY KEY, command TEXT, ... );
CREATE TABLE migrations ( id INTEGER PRIMARY KEY, version INTEGER NOT NULL, migration_time INTEGER NOT NULL );
CREATE TABLE state ( key TEXT PRIMARY KEY, value TEXT );
INSERT INTO migrations (version, migration_time) VALUES
    (0, 1700000000),
    (1, 1700000000),
    (2, 1700000000),
    (3, 1700000000),
    (4, 1700000000),
    (5, 1700000000);
""")
```

If 0.9.0's kiro-cli applies migrations `6..M`, a crew seeded with `max_version 5`
presents a DB that kiro-cli considers already-migrated-to-5. Depending on how
0.9.0's startup reconciles that, either (a) it re-runs migrations `6..M` at launch
(reintroducing the migration-wait/restart this seed exists to avoid), or (b) it
mismatches the expected table set so `inject_auth.py`'s INSERT into `auth_kv` fails
(`no such table: auth_kv`, or missing columns). Both are launch-time, not
build-time — the image builds green and the failure is silent until first auth.

### 2.1 Procedure

1. Pull and inspect the target base image's actual schema:
   ```bash
   podman run --rm ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4 python3 -c \
     "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
      print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone()); \
      print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()])"
   ```
2. **If the tuple is `(6, 5)` and the table set is unchanged**: the only edit is the
   ⚠️ header annotation — bump `KiroCrew 0.8.0 / kiro-cli 2.27.1` to the 0.9.0 /
   kiro-cli version string, change `Verified 2026-10-09 against ...:0.8.0: result
   (6, 5)` to the new tag/date/result. The `executescript` and INSERT stay as-is.
3. **If the tuple differs** (say `(8, 7)`): extend the INSERT to versions `0..7`
   (eight rows, same `1700000000` placeholder `migration_time`), and reconcile the
   `CREATE TABLE` statements against the inspected table set — add any new table,
   drop any removed one, and adjust columns on `auth_kv`/`history`/`state` if the
   0.9.0 schema widened them. Keep `auth_kv (key TEXT PRIMARY KEY, value TEXT)`
   present and correct, because `inject_auth.py` depends on it.
4. Update the "Removed vs ..." provenance line in the docstring to describe the
   actual 0.9.0 delta rather than the 0.5.0→0.8.0 one.

## 3. admission/Containerfile — bump the KC_BASE_IMAGE default

`crews/_base/admission/Containerfile` declares the base-image build-arg:

```dockerfile
ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.8.0
FROM ${KC_BASE_IMAGE}
```

The in-file comment states the invariant: *"Default here matches the config default
so plain `podman build` still works."* So the edit is two-sided and must stay in
sync:

- `admission/Containerfile`: `ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`
- `ghostship.conf` (and `ghostship.conf.example`): `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`

Prefer the immutable digest form
(`ghcr.io/kirodotdev/kirocrew@sha256:f4f4801898572175a1988e61a8696769821528860edceaf5ca253f8123a77009`)
so a rebuild cannot float onto a newer insider silently. This bump MUST land in the
same change as the seed re-verification (step 2) — bumping the FROM pin without the
seed check is exactly the regression this proposal guards against.

## 4. Build-order and ordering constraints

Per the admission Containerfile header, the build order is:
`localhost/base-admission` → `localhost/<comp>-mid` → `localhost/<comp>`
(graduation). The seed in `seed_kiro_db.py` is applied by the graduation layer,
which runs *after* the composition. So the sequencing within this change is:

1. Verify + update `seed_kiro_db.py` (step 2) — **first**, so the graduation layer
   seeds the correct schema.
2. Bump `KC_BASE_IMAGE` in `admission/Containerfile` + `ghostship.conf` (step 3).
3. Full clean rebuild (`install.sh` forces cache-less rebuild on build-arg change —
   the `LABEL org.ghostship.toolchains` / `AGENT_TOOLCHAINS` mechanism in
   `spec-ops/Containerfile` shows podman reuses layers on arg-only changes, so a
   base-image bump needs an explicit no-cache rebuild of the admission layer).
4. Launch a throwaway crew and confirm an agent authenticates (auth insert
   succeeded) before release.

## 5. Rollback

If the 0.9.0 crew fails auth after the bump, revert `KC_BASE_IMAGE` to
`ghcr.io/kirodotdev/kirocrew:0.8.0` in both locations and restore the 0.8.0
`seed_kiro_db.py` (git revert of this change's commit). Because the seed is
build-time data, rollback is a rebuild, not a data migration.
