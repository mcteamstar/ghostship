# Manual Test Procedure: Dedicated Podman Machine

This document describes how to verify the dedicated Podman machine feature
end-to-end on a real system. These tests cannot be fully automated because
they require an actual Podman runtime (machine on macOS, systemd on Linux).

## Prerequisites

- Podman >= 4.0 installed
- macOS: Podman Desktop or `brew install podman`
- Linux: systemd user session (`loginctl enable-linger` recommended)
- This repository cloned locally

## Test 1: Fresh Install with Dedicated Machine (macOS)

```bash
# 1. Create a config file enabling the dedicated machine
cat > /tmp/test-dedicated.conf <<EOF
GA_DEDICATED_MACHINE=true
GA_MACHINE_CPUS=2
GA_MACHINE_MEMORY=4096
GA_MACHINE_DISK=30
GA_MACHINE_NAME=ghost-academy
PORT=64057
EOF

# 2. Run install
./install.sh --config /tmp/test-dedicated.conf

# 3. Verify the dedicated machine exists
podman machine list
# Expected: two machines — "default" (or whatever existed before) AND "ghost-academy"

# 4. Verify crew containers are on the dedicated machine
podman machine ssh ghost-academy -- podman ps
# Expected: ga-transport is running

# 5. Verify the default machine is unaffected
podman ps
# Expected: no ga-transport (it's on the other machine)
```

**Pass criteria:** `podman machine list` shows `ghost-academy`, transport is
healthy on `http://127.0.0.1:64057/health`.

## Test 2: Fresh Install with Dedicated Machine (Linux)

```bash
# 1. Create config
cat > /tmp/test-dedicated.conf <<EOF
GA_DEDICATED_MACHINE=true
GA_MACHINE_NAME=ghost-academy
PORT=64057
EOF

# 2. Run install
./install.sh --config /tmp/test-dedicated.conf

# 3. Verify systemd units
systemctl --user status podman-ghost-academy.socket
# Expected: active (listening)

# 4. Verify socket exists
ls -la /run/user/$(id -u)/podman/ghost-academy.sock
# Expected: socket file present

# 5. Verify containers on dedicated instance
podman --root=~/.local/share/ghost-academy/containers/storage \
  --runroot=$XDG_RUNTIME_DIR/ghost-academy-containers ps
# Expected: ga-transport running

# 6. Verify default instance is clean
podman ps
# Expected: no ga-transport
```

**Pass criteria:** Socket is active, transport is healthy, default `podman ps`
doesn't show GA containers.

## Test 3: Idempotency — Second Install Doesn't Re-init

```bash
# Run install again with the same config
./install.sh --config /tmp/test-dedicated.conf

# Verify:
# - No "Initialising dedicated podman machine" message (macOS)
# - No "writing unit files" message if already present (Linux)
# - Transport restarts cleanly
# - Health check passes
```

**Pass criteria:** No machine re-init, transport healthy after second run.

## Test 4: Fallback — Disabled Dedicated Machine

```bash
# 1. Config with dedicated machine disabled
cat > /tmp/test-default.conf <<EOF
GA_DEDICATED_MACHINE=false
PORT=64057
EOF

# 2. Run install
./install.sh --config /tmp/test-default.conf

# 3. Verify default behaviour
podman ps
# Expected: ga-transport running on the DEFAULT instance
# (macOS: default machine; Linux: default podman.socket)
```

**Pass criteria:** Behaviour identical to pre-feature install.

## Test 5: Uninstall Removes Dedicated Machine

```bash
# 1. First, ensure a dedicated install exists (run Test 1 or 2 first)

# 2. Uninstall
./uninstall.sh --yes

# 3. Verify cleanup (macOS)
podman machine list
# Expected: "ghost-academy" machine is gone

# 3. Verify cleanup (Linux)
systemctl --user status podman-ghost-academy.socket 2>&1
# Expected: "could not be found" or "inactive"
ls ~/.local/share/ghost-academy/containers/ 2>&1
# Expected: directory removed (containers/ is wiped)
ls ~/.local/share/ghost-academy/data/ 2>&1
# Expected: data/ still present (ga-kiro-auth preserved unless --purge-auth)
```

**Pass criteria:** No containers/storage traces remain; `data/ga-kiro-auth` is preserved.

## Test 6: Uninstall with --keep-machine

```bash
# 1. Ensure a dedicated install exists

# 2. Uninstall with --keep-machine
./uninstall.sh --yes --keep-machine

# 3. Verify machine/storage is preserved
# macOS:
podman machine list  # ghost-academy still present
# Linux:
ls ~/.local/share/ghost-academy/  # directory preserved
```

**Pass criteria:** Machine/storage preserved, all containers and GA
resources still removed.

## Test 7: Named Connection Verification (macOS)

```bash
# After install with dedicated machine:
podman system connection list
# Expect to see default + ghost-academy connections

# Query dedicated machine directly:
podman --connection ghost-academy ps
# Expected: shows ga-transport and crew containers
```

## Checklist Summary

| # | Test | macOS | Linux |
|:--|:-----|:-----:|:-----:|
| 1 | Fresh install with dedicated machine | ○ | — |
| 2 | Fresh install with dedicated instance | — | ○ |
| 3 | Idempotent re-install | ○ | ○ |
| 4 | Fallback (GA_DEDICATED_MACHINE=false) | ○ | ○ |
| 5 | Uninstall removes dedicated machine | ○ | ○ |
| 6 | Uninstall --keep-machine | ○ | ○ |
| 7 | Named connection (macOS only) | ○ | — |

Mark each cell with ✓ (pass) or ✗ (fail) when running the procedure.
