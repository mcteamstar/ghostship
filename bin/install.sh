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

# ── Exec into Python entry point ─────────────────────────────────────────────
export GHOSTSHIP_DIR OS
exec python3 "${GHOSTSHIP_DIR}/bin/lib/install_main.py" "$@"
