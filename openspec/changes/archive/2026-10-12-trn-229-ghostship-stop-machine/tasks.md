# Tasks

## 1. Implementation

- [x] 1.1 In `ghostship` CLI (`cmd_stop`): load config to resolve `GA_MACHINE_NAME` (default `ghost-academy`) and `GA_DEDICATED_MACHINE` (default `true`). Stop `ga-portal` in addition to `ga-transport`. Then stop the Podman machine (macOS) or dedicated systemd service (Linux) per the design. Handle already-stopped machine gracefully (exit 0). Verify: `ghostship stop` on macOS stops the machine — `podman machine list` shows it as stopped; `ghostship start` brings it back.

## 2. Tests

- [x] 2.1 In `tests/unit/test_ghostship_cli.py`, add a test for `cmd_stop` on macOS: mock `_podman_cmd`, `subprocess.run`, and `platform.system` → assert `podman machine stop ghost-academy` is called after the container stops. Verify: `tests/run.sh --unit` passes.
- [x] 2.2 Add a test for Linux dedicated: mock `platform.system` → `"Linux"`, `GA_DEDICATED_MACHINE=true` → assert `systemctl --user stop podman-ghost-academy.service` is called. Verify: test passes.
- [x] 2.3 Add a test for already-stopped machine (non-zero return from machine stop) → assert `cmd_stop` exits 0 with a message rather than failing. Verify: test passes.

## 3. Docs

- [x] 3.1 Update `ghostship --help` string in `ghostship` CLI (`cmd_stop` docstring / help text) to reflect the new behaviour. Verify: `ghostship stop --help` or `ghostship --help` describes the full stop sequence.

## Workflow follow-up

- Archive the change after tests pass and PR is merged.
