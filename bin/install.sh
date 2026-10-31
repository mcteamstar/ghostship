#!/usr/bin/env bash
# Install/update Ghost Academy locally on macOS or Linux.
#
# Usage:
#   ./install.sh [--config <path>] [--identity-provider <url>] \
#                [--region <region>] [--port <port>] \
#                [--model <model>] [--api-key <key>] \
#                [--caddy-domain <domain>] [--caddy-tls-mode <mode>] \
#                [--client-only] [--url <url>] [--wizard]
#
# All logic is in bin/lib/install_main.py; this shim validates prerequisites
# and execs into Python to avoid any eval injection surface.
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"

# ── Prereq: python3 ───────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2
  exit 1
fi

# ── Prereq: podman ────────────────────────────────────────────────────────────
if ! command -v podman >/dev/null 2>&1; then
  echo "✗ podman not found." >&2
  case "$OS" in
    Darwin) echo "  brew install podman" >&2 ;;
    Linux)  echo "  sudo apt-get install -y podman podman-compose" >&2 ;;
  esac
  exit 1
fi

# ── Prereq: podman-compose ───────────────────────────────────────────────────
if ! command -v podman-compose >/dev/null 2>&1; then
  echo "✗ podman-compose not found." >&2
  case "$OS" in
    Darwin) echo "  brew install podman-compose" >&2 ;;
    Linux)  echo "  sudo apt-get install -y podman-compose" >&2 ;;
  esac
  exit 1
fi

# ── Podman provisioning (machine/instance) ───────────────────────────────────
# GA_MACHINE_NAME and GA_DEDICATED_MACHINE may still be at defaults; they get
# overridden by the config file inside install_main.py for the full install.
# For Podman provisioning we need a best-effort value from the environment,
# which for a first-time install matches the built-in defaults.
GA_MACHINE_NAME="${GA_MACHINE_NAME:-ghost-academy}"
GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE:-true}"

PODMAN_SOCK="$(
  GA_MACHINE_NAME="${GA_MACHINE_NAME}" \
  GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE}" \
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
  PODMAN_SOCK="${PODMAN_SOCK:-}" \
  python3 "${GHOSTSHIP_DIR}/bin/lib/podman_setup.py" --print-socket
)" || { echo "✗ Failed to resolve Podman socket path" >&2; exit 1; }

GA_MACHINE_NAME="${GA_MACHINE_NAME}" \
GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE}" \
GA_MACHINE_CPUS="${GA_MACHINE_CPUS:-8}" \
GA_MACHINE_MEMORY="${GA_MACHINE_MEMORY:-16384}" \
GA_MACHINE_DISK="${GA_MACHINE_DISK:-100}" \
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}" \
PODMAN_SOCK="${PODMAN_SOCK}" \
python3 "${GHOSTSHIP_DIR}/bin/lib/podman_setup.py" \
  || { echo "✗ Podman provisioning failed" >&2; exit 1; }

# ── DATA_DIR ─────────────────────────────────────────────────────────────────
if [[ "$OS" == "Darwin" ]]; then
  DATA_DIR="$HOME/Library/Application Support/${GA_MACHINE_NAME}/data"
else
  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${GA_MACHINE_NAME}/data"
fi
mkdir -p "$DATA_DIR"

# ── Exec into Python entry point ─────────────────────────────────────────────
export GHOSTSHIP_DIR OS PODMAN_SOCK DATA_DIR
exec python3 "${GHOSTSHIP_DIR}/bin/lib/install_main.py" "$@"
