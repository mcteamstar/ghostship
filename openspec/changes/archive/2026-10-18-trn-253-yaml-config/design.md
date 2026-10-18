# Design

## Context

See proposal.md — Why. The current `ghostship.conf` is shell-sourced by install.sh
via `source`. The transport never reads it directly — install.sh bakes resolved values
into `compose.yml` as `environment:` entries, which the transport reads via
`os.environ`. The `Config` dataclass in `transport/config.py` is the transport's
authoritative config schema; `Config.from_env()` is the only place it reads
`os.environ`.

The config file lives at `config/ghostship.conf` in the repo and is gitignored. The
example (`config/ghostship.conf.example`) is committed. A CI sync test asserts that
every `Config` field has a corresponding entry in the example file.

## Goals / Non-Goals

**Goals:**
- Replace `ghostship.conf` with `ghostship.yaml` with no loss of configured behaviour
- Three-layer deep merge (defaults → repo → XDG, or defaults → `--config`)
- Auto-migration from existing `ghostship.conf` on install
- Maintain the CI sync invariant for the new example file
- Keep `Config.from_env()` as the transport's config path (env vars still baked into compose.yml)

**Non-Goals:**
- Transport reading `ghostship.yaml` directly (env var injection via compose.yml is preserved)
- `ghostship config set` CLI command (no programmatic config writes)
- Hot-reload of config without container restart
- YAML validation beyond unknown key warnings (schema errors fail at install time)

## Decisions

### D1 — PyYAML for parsing, no ruamel.yaml

install.sh shells out to Python for YAML parsing (`python3 -c "import yaml; ..."`).
PyYAML is sufficient since config files are never written back. ruamel.yaml (which
preserves comments through round-trips) is not needed and adds a dependency.

The transport itself does not parse YAML — `Config.from_env()` is unchanged. install.sh
resolves config and bakes values into compose.yml env entries as before.

**Alternative considered:** bash-native YAML parsing (yq or manual awk). Rejected —
introduces another tool dependency and the parsing logic would be complex for nested
structures and deep merge.

### D2 — Deep merge implemented in Python, called from install.sh

install.sh contains a Python helper (heredoc or inline) that:
1. Loads built-in defaults as a dict (mirroring Config field defaults)
2. Loads and merges `config/ghostship.yaml` if present
3. Loads and merges XDG override if present (or `--config` file, exclusively)
4. Returns the merged flat env var dict for install.sh to use

Deep merge is recursive: for dict values, merge key-by-key; for scalar values, later
layer wins. Lists are replaced entirely (not concatenated).

**Alternative considered:** Merge in bash via multiple yaml-to-env passes. Rejected —
bash has no native dict merge; the Python approach is cleaner and testable.

### D3 — YAML keys map to existing env var names (flattened)

The YAML structure is:
```yaml
network:
  port: 64057       → PORT
crew:
  max_active: 3     → GA_MAX_ACTIVE_CREWS
backends:
  kiro:
    identity_provider: ""  → KIRO_IDENTITY_PROVIDER
```

The Python merge helper flattens the merged dict to env var names before returning
to install.sh. The mapping table is defined once in the Python helper.

This keeps `Config.from_env()` unchanged — the transport still reads `PORT`,
`GA_MAX_ACTIVE_CREWS` etc. from the environment. No transport code changes for the
basic migration.

**Alternative considered:** Transport reads YAML directly via a new `Config.from_yaml()`.
Deferred to a future change — it would require mounting the config file into the
container, changing the volume setup, and the transport's startup path. The env var
approach gives us YAML config with minimal blast radius for 0.8.0.

### D4 — Auto-migration: mechanical key mapping

The migration from `ghostship.conf` to `ghostship.yaml` is a mechanical key→path
mapping (e.g. `PORT=9000` → `network:\n  port: 9000`). install.sh runs the migration
Python helper when `config/ghostship.conf` exists without `config/ghostship.yaml`.

The generated `ghostship.yaml` contains only the keys that were set in `ghostship.conf`
(non-default values), plus inline comments for each. Default-value keys are omitted —
consistent with the "override files" principle.

### D5 — XDG path per OS

- macOS: `~/Library/Application Support/ghost-academy/ghostship.yaml`
- Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/ghost-academy/ghostship.yaml`

The macOS path matches the existing data volume convention (`~/Library/Application
Support/ghost-academy/data/`), keeping all ghost-academy files in one location.

### D6 — `--config` flag replaces implicit resolution entirely

When `--config` is passed, the repo and XDG layers are skipped. The `--config` file
merges only on top of built-in defaults. This ensures predictable behaviour for CI,
remote deploys, and scripted installs where the operator wants full control.

### D7 — Wizard generates from internal template

The wizard writes `config/ghostship.yaml` from an internal bash heredoc template with
all keys commented out at their defaults, plus operator-supplied values uncommented.
This avoids PyYAML round-trip (which strips comments) and keeps the wizard output
human-readable. The `.example` file is separate — documentation only.

## Migration Plan

1. **install.sh** detects `config/ghostship.conf` + no `config/ghostship.yaml`:
   - Runs migration helper (Python): reads conf, maps keys to YAML paths, writes `config/ghostship.yaml` with only non-default values
   - Renames `config/ghostship.conf` → `config/ghostship.conf.bak`
   - Prints: `Config migrated to config/ghostship.yaml. Old file kept as config/ghostship.conf.bak.`
2. Install proceeds with the migrated file.
3. **Rollback**: rename `config/ghostship.conf.bak` back to `config/ghostship.conf` and downgrade.

**Pre-0.8.0 warning**: The upgrade prompt added in TRN-233 already catches pre-0.8.0
installs. The config migration notice adds a second clear signal that the config format
has changed.

## Risks / Trade-offs

- **YAML syntax errors in operator config** → install.sh prints a clear error with line
  number and aborts. The operator must fix the file before retalling.

- **Key mapping gaps in auto-migration** → Any `ghostship.conf` key not in the
  mapping table is emitted as a YAML comment `# UNKNOWN: KEY=value` in the migrated
  file, so the operator can handle it manually. Install prints a warning listing any
  unknown keys found.

- **`Config.from_env()` unchanged** → The transport still reads env vars, not YAML
  directly. This means the YAML layer only applies at install time, not at transport
  runtime. A future change (D3 alternative) could mount the YAML file and have the
  transport read it directly, enabling config changes without reinstalling. Deferred.

- **Deep merge of lists** → Lists are replaced entirely. `backends.enabled: [kiro, claude]`
  in the XDG file replaces `[kiro]` from the repo, not extends it. This is simpler and
  more predictable than list merging.

## Open Questions

None — all decisions required for the task breakdown are resolved above.
