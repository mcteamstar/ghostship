# Design

## Context

`cmd_stop` in `ghostship` currently runs `podman stop ga-transport` only. The Podman machine (macOS) or dedicated service (Linux) stays up. `ga-portal` is not stopped either.

The platform detection and config resolution logic already exists in `start.sh` and `install.sh` — this change mirrors their patterns inside the Python CLI.

## Goals / Non-Goals

**Goals:**
- Stop `ga-transport` and `ga-portal`
- Stop the Podman machine (macOS) or dedicated systemd service (Linux)
- Exit 0 gracefully if machine is already stopped or not found
- Stay consistent with how `start.sh` detects platform and machine name

**Non-Goals:**
- Adding a separate `ghostship sleep` subcommand (stop now does the full job)
- Changing `ghostship start` (already handles machine restart)
- Stopping crews explicitly (they stop with the machine; volumes preserved)

## Decisions

**Read config before stopping** — `cmd_stop` needs `GA_MACHINE_NAME` and `GA_DEDICATED_MACHINE`. These are read from the environment via `os.environ.get()` — the same pattern `_podman_cmd()` already uses. No config-file loading is needed; `install.sh` writes these into the compose environment, and operators who set them in `ghostship.conf` will have them sourced before calling `ghostship stop`.

**Platform detection in Python** — `platform.system()` gives `"Darwin"` or `"Linux"`. Mirror the `start.sh` logic directly.

**macOS stop sequence:**
```python
# 1. Stop containers
podman_conn = ["podman", "--connection", machine_name]
subprocess.run(podman_conn + ["stop", "ga-transport", "ga-portal"], ...)
# 2. Stop machine
subprocess.run(["podman", "machine", "stop", machine_name], ...)
```

**Linux dedicated stop sequence:**
```python
# 1. Stop containers via the socket
env_podman = ["env", f"CONTAINER_HOST=unix://{sock}", "podman"]
subprocess.run(env_podman + ["stop", "ga-transport", "ga-portal"], ...)
# 2. Stop the systemd service
subprocess.run(["systemctl", "--user", "stop", f"podman-{machine_name}.service"], ...)
```

**Linux non-dedicated stop:**
```python
subprocess.run(["podman", "stop", "ga-transport", "ga-portal"], ...)
subprocess.run(["systemctl", "--user", "stop", "podman.socket"], ...)
```

**Graceful missing-machine handling** — wrap the machine stop in a try/except; a non-zero return from `podman machine stop` when the machine is already stopped is not an error.

## Risks / Trade-offs

**Breaking change for scripts that call `ghostship stop` to just bounce the transport** — previously stop left the machine running so containers came back fast. Now stop tears down the machine. Anyone relying on a quick restart would need `ghostship start` (which already works). The tradeoff is acceptable: the primary use case for stop is "free RAM", not "quick bounce" (for which `ghostship upgrade` / `install` is the right tool anyway).
