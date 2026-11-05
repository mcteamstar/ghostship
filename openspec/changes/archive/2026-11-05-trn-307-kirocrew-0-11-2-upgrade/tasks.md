# Tasks

## 1. Obtain digest and verify seed

- [x] 1.1 Run `podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.2` and record the multi-arch index digest (wait for image to propagate to registry if not yet available)
- [x] 1.2 Run the migration verification command against the v0.11.2 image and record the result:
  ```bash
  podman run --rm ghcr.io/kirodotdev/kirocrew:v0.11.2 python3 -c \
    "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
    print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
  ```
  Expected: `(6, 5)` — if different, update `seed_kiro_db.py` migration rows before proceeding

## 2. Update base image pin

- [x] 2.1 `crews/_base/admission/Containerfile`: update `KC_BASE_IMAGE` default to the v0.11.2 digest; update the comment block (version `v0.11.2`, commit `31ee6e4`, date `2026-11-04`, new digest)
- [x] 2.2 `crews/_base/graduation/seed_kiro_db.py`: update the verification annotation comment to reference v0.11.2, the verification date, and the observed migration result (migration rows unchanged if result is `(6, 5)`)
- [x] 2.3 `transport/config.py`: update the comment referencing `v0.11.1 stable` → `v0.11.2 stable`

## 3. Rebuild and smoke test

- [x] 3.1 Run `./install.sh` on the deployment host to rebuild the crew image with the new base; verify the build completes without errors
- [x] 3.2 Launch a test crew on the deployment host, dispatch a trivial ghost task, and verify the agent authenticates and runs without errors; verify `ghostship status` shows the transport healthy

## 4. Changelog and version

- [x] 4.1 Add a `v0.11.3` entry to `CHANGELOG.md` describing the KiroCrew v0.11.2 base image bump
- [x] 4.2 Bump `VERSION`, `.claude-plugin/plugin.json`, nested `plugin.json`, and all three `SKILL.md` version fields to `0.11.3`

## Workflow follow-up

- Archive the change after implementation is verified.
- Commit and push `release/0.11.2` (or open a new `release/0.11.3` branch if preferred).
