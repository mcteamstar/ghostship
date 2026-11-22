#!/usr/bin/env bash
# Exercise Podman's size-limited tmpfs with the same rootless engine used by
# Ghostship. Run after `ghostship install` on Linux and macOS Podman.
set -euo pipefail

podman_bin="${PODMAN:-podman}"
image="${GA_TMPFS_TEST_IMAGE:-localhost/transport:latest}"
limit_bytes=16777216

if ! command -v "$podman_bin" >/dev/null 2>&1; then
  echo "Podman is required for this rootless tmpfs check." >&2
  exit 2
fi

rootless="$($podman_bin info --format '{{.Host.Security.Rootless}}')"
if [[ "$rootless" != "true" ]]; then
  echo "This check must run against rootless Podman (reported: $rootless)." >&2
  exit 1
fi

"$podman_bin" run --rm --network=none \
  --tmpfs "/ga-bundle-storage:rw,nosuid,nodev,noexec,size=${limit_bytes},mode=1777" \
  -e "GA_TMPFS_EXPECTED_LIMIT=$limit_bytes" \
  "$image" python3 -c '
import errno, os, sys

limit = int(os.environ["GA_TMPFS_EXPECTED_LIMIT"])
root = "/ga-bundle-storage"
stat = os.statvfs(root)
block_size = stat.f_frsize or stat.f_bsize
capacity = stat.f_blocks * block_size
if capacity > limit:
    raise SystemExit(f"tmpfs capacity {capacity} exceeds configured limit {limit}")
mounted_tmpfs = False
with open("/proc/self/mountinfo", encoding="utf-8") as mounts:
    for line in mounts:
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        filesystem = after.split()
        if len(fields) >= 5 and filesystem and fields[4] == root and filesystem[0] == "tmpfs":
            mounted_tmpfs = True
            break
if not mounted_tmpfs:
    raise SystemExit("configured path is not backed by a tmpfs mount")

written = 0
try:
    with open(os.path.join(root, "fill"), "wb", buffering=0) as output:
        chunk = b"x" * 65536
        while True:
            written += output.write(chunk)
except OSError as exc:
    if exc.errno != errno.ENOSPC:
        raise

if written > limit:
    raise SystemExit(f"tmpfs accepted {written} bytes above limit {limit}")
print(f"rootless tmpfs stopped writes at {written} bytes (capacity {capacity})")
'
