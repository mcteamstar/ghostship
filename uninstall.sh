#!/usr/bin/env bash
# Uninstall Ghost Academy's local install: tears down everything install.sh
# creates that is safe to remove automatically. Deliberately leaves alone
# anything shared with other Podman workloads on this machine — see the
# "Left alone" section printed at the end.
#
# Run:
#   ./uninstall.sh [--yes] [--purge-auth]
#
#   --yes         Skip the confirmation prompt.
#   --purge-auth  Also remove the ga-kiro-auth file. Off by default —
#                 removing it means the next install needs a fresh device
#                 auth login instead of inheriting the existing one.
set -eo pipefail

OS="$(uname -s)"
YES=""
PURGE_AUTH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES="1"; shift ;;
    --purge-auth) PURGE_AUTH="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ "$OS" == "Darwin" ]]; then
  DATA_DIR="$HOME/Library/Application Support/ghostship/data"
else
  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/ghostship/data"
fi

echo "This will remove:"
echo "  - ga-transport container"
echo "  - any live crew containers (gs-<crew_id>) and their volumes (gs-vol-*, gs-home-*)"
echo "  - ga-net network"
echo "  - localhost/kirocrew-crew:latest and localhost/transport:latest images"
if [[ -n "$PURGE_AUTH" ]]; then
  echo "  - transport state under ${DATA_DIR}, including the ga-kiro-auth file (--purge-auth given — next install needs a fresh login)"
else
  echo "  - transport state under ${DATA_DIR} (${DATA_DIR}/ga-kiro-auth is KEPT — pass --purge-auth to remove it)"
fi
echo ""
echo "Left alone (shared with other Podman workloads on this machine):"
echo "  - podman itself, podman-restart.service, podman.socket"
echo "  - the podman machine VM (macOS)"
echo "  - the ghcr.io/kirodotdev/kirocrew:stable base image"
echo ""

if [[ -z "$YES" ]]; then
  read -rp "Proceed? [y/N] " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted."; exit 0; }
fi

# ── Crews ─────────────────────────────────────────────────────────────────────
# gs-* is per-crew ghostship resources only — ga-transport/ga-net use the
# separate ga- prefix, so this filter can never touch them.

echo ""
echo "Removing crew containers + volumes..."
for c in $(podman ps -a --filter name=^gs- --format '{{.Names}}' 2>/dev/null); do
  podman rm -f "$c" >/dev/null 2>&1 && echo "  removed container: $c"
done
for v in $(podman volume ls --filter name=gs-vol- --format '{{.Name}}' 2>/dev/null); do
  podman volume rm -f "$v" >/dev/null 2>&1 && echo "  removed volume: $v"
done
for v in $(podman volume ls --filter name=gs-home- --format '{{.Name}}' 2>/dev/null); do
  podman volume rm -f "$v" >/dev/null 2>&1 && echo "  removed volume: $v"
done

# ── Transport ─────────────────────────────────────────────────────────────────

podman rm -f ga-transport >/dev/null 2>&1 && echo "✓ ga-transport container removed" || echo "  (ga-transport was not running)"
podman network rm ga-net >/dev/null 2>&1 && echo "✓ ga-net network removed" || echo "  (ga-net did not exist)"

# ── Images ────────────────────────────────────────────────────────────────────

podman rmi -f localhost/kirocrew-crew:latest >/dev/null 2>&1 && echo "✓ localhost/kirocrew-crew:latest removed" || true
podman rmi -f localhost/transport:latest >/dev/null 2>&1 && echo "✓ localhost/transport:latest removed" || true

# ── Data dir ──────────────────────────────────────────────────────────────────

AUTH_FILE="${DATA_DIR}/ga-kiro-auth"
if [[ -d "$DATA_DIR" ]]; then
  shopt -s dotglob nullglob
  for entry in "$DATA_DIR"/*; do
    [[ "$entry" == "$AUTH_FILE" ]] && continue
    rm -rf "$entry"
  done
  shopt -u dotglob nullglob

  if [[ -n "$PURGE_AUTH" ]]; then
    if [[ -e "$AUTH_FILE" || -L "$AUTH_FILE" ]]; then
      rm -f "$AUTH_FILE"
      echo "✓ removed ${AUTH_FILE}"
    fi
    echo "✓ removed transport state from ${DATA_DIR}"
  else
    echo "✓ removed transport state from ${DATA_DIR} (kept ${AUTH_FILE})"
  fi
fi

echo ""
echo "=== Done ==="
echo "Not automated — remove these yourself if you registered them:"
echo "  kiro-cli mcp remove --name ghostship --scope global"
echo "  Claude Code: delete the \"ghostship\" entry from ~/.claude.json's mcpServers"
