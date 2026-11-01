#!/usr/bin/env bash
# Start Ghost Academy.  Requires install.sh to have been run first.
# Usage: ./start.sh [--config <path>] [--machine-name <name>]
#
# All logic is in bin/lib/start_main.py; this shim checks prerequisites
# and execs into Python.
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2; exit 1
fi

if ! command -v podman >/dev/null 2>&1; then
  echo "✗ podman not found." >&2
  case "$OS" in
    Darwin) echo "  brew install podman" >&2 ;;
    Linux)  echo "  sudo apt-get install -y podman podman-compose" >&2 ;;
  esac
  exit 1
fi

if ! command -v podman-compose >/dev/null 2>&1; then
  echo "✗ podman-compose not found." >&2
  case "$OS" in
    Darwin) echo "  brew install podman-compose" >&2 ;;
    Linux)  echo "  sudo apt-get install -y podman-compose" >&2 ;;
  esac
  exit 1
fi

export GHOSTSHIP_DIR OS
exec python3 "${GHOSTSHIP_DIR}/bin/lib/start_main.py" "$@"
