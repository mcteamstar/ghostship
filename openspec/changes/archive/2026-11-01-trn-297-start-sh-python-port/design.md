# TRN-297 — Design

## Architecture

`bin/start.sh` becomes a thin shim identical in structure to `bin/install.sh`:

```bash
#!/usr/bin/env bash
# prereq checks (python3, podman, podman-compose)
# ...
exec python3 "${GHOSTSHIP_DIR}/bin/lib/start_main.py" "$@"
```

`bin/lib/start_main.py` orchestrates:

1. **Config resolution** — call `start_ops.resolve_start_config(ghostship_dir, config_path)` (or inline via `yaml_config`) to get `GA_MACHINE_NAME`, `GA_DEDICATED_MACHINE`, `PORT`, `HOST`, `GA_PORTAL_TLS_MODE`
2. **Podman start** — call `podman_setup.setup_podman(config)` (already handles macOS machine start + Linux socket); reuse the existing `PodmanConfig` dataclass
3. **Compose up** — `subprocess.run(["podman", "compose", "--project-name", "ga", "-f", compose_file, "up", "-d"], env=..., check=True)` — no eval, env vars passed explicitly via `env=` dict
4. **Health check** — `urllib.request.urlopen` loop (already used in `install_main.py`) against `probe_url/health`
5. **Exit** — print status, exit 0

## Module reuse

| Need | Module |
|:-----|:-------|
| Machine start / socket | `podman_setup.py` — `setup_podman()` |
| Config resolution | `start_ops.py` + `yaml_config.py` |
| Health check URL | `portal_host.py` — `probe_base()` |
| Compose env construction | Inline — explicit `env` dict, no eval |

## Affected files

| File | Change |
|:-----|:-------|
| `bin/start.sh` | Reduce from 170 → ~30 lines; prereq check + exec |
| `bin/lib/start_main.py` | New — ~120 lines |
| `bin/lib/start_ops.py` | Minor extension if needed |
| `tests/unit/test_start_main.py` | New — unit tests for start_main |

## Verification

- `bash -n bin/start.sh` passes
- `wc -l bin/start.sh` ≤ 40
- `grep -c eval bin/start.sh` = 0
- `pytest tests/unit/test_start_main.py` passes
- `ghostship upgrade && ghostship start` works end-to-end on corsair
