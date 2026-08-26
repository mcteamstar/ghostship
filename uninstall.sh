#!/usr/bin/env bash
# Uninstall Ghost Academy's local install: tears down everything install.sh
# creates that is safe to remove automatically. Deliberately leaves alone
# anything shared with other Podman workloads on this machine — see the
# "Left alone" section printed at the end.
#
# Run:
#   ./uninstall.sh [--config <path>] [--yes] [--purge-auth] [--keep-machine]
#
#   --config <path> Same config file passed to install.sh — read here only
#                    for GA_MACHINE_NAME, so a customised dedicated-machine
#                    name is actually found and torn down.
#   --yes           Skip the confirmation prompt.
#   --purge-auth    Also remove the ga-kiro-auth file. Off by default —
#                   removing it means the next install needs a fresh device
#                   auth login instead of inheriting the existing one.
#                   On Linux, this is the only flag that removes ga-kiro-auth;
#                   omitting --keep-machine does NOT remove it.
#   --keep-machine  Keep the dedicated Podman machine/instance (don't remove
#                   the VM on macOS or the containers/ storage root on Linux).
#                   Useful if you plan to re-install soon.
set -eo pipefail

OS="$(uname -s)"
YES=""
PURGE_AUTH=""
KEEP_MACHINE=""
CONFIG_FILE=""

# ── Built-in defaults (literal assignments, BEFORE config sourcing) ──────────
# Resolution order: built-in default → config file (no CLI flags for these).
GA_DEDICATED_MACHINE=true
GA_MACHINE_NAME=ghost-academy

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_FILE="$2"; shift 2 ;;
    --yes) YES="1"; shift ;;
    --purge-auth) PURGE_AUTH="1"; shift ;;
    --keep-machine) KEEP_MACHINE="1"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -n "$CONFIG_FILE" ]]; then
  if [[ ! -r "$CONFIG_FILE" ]]; then
    echo "Error: config file does not exist or is not readable: $CONFIG_FILE" >&2
    exit 1
  fi
  # Same trust assumption as install.sh: this sources arbitrary shell code
  # from the path the caller passed. Do NOT pass an untrusted path.
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  echo "✓ Sourced config file: $CONFIG_FILE"
fi

# ── Detect dedicated machine/instance ─────────────────────────────────────────
# Check if a dedicated machine/instance exists so we can clean it up.
# GA_MACHINE_NAME honours the same env var / --config file as install.sh, so
# a customised name is actually found instead of silently left behind.
# NOTE: _MACHINE_NAME must be set before DATA_DIR so it expands correctly.
_HAS_DEDICATED_MACHINE=""
_MACHINE_NAME="$GA_MACHINE_NAME"

if [[ "$OS" == "Darwin" ]]; then
  DATA_DIR="$HOME/Library/Application Support/${_MACHINE_NAME}/data"
else
  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${_MACHINE_NAME}/data"
fi

if [[ "$OS" == "Darwin" ]]; then
  if podman machine list --format '{{.Name}}' 2>/dev/null | grep -qw "${_MACHINE_NAME}"; then
    _HAS_DEDICATED_MACHINE="1"
  fi
else
  _UNIT_DIR="${HOME}/.config/systemd/user"
  if [[ -f "${_UNIT_DIR}/podman-${_MACHINE_NAME}.socket" ]] \
     || [[ -f "${_UNIT_DIR}/podman-${_MACHINE_NAME}.service" ]]; then
    _HAS_DEDICATED_MACHINE="1"
  fi
fi

echo "This will remove:"
echo "  - ga-transport container"
echo "  - any live crew containers (gs-<crew_id>) and their volumes (gs-vol-*, gs-home-*)"
echo "  - ga-net network"
echo "  - localhost/kirocrew-crew:latest and localhost/transport:latest images"
if [[ -n "$_HAS_DEDICATED_MACHINE" ]]; then
  if [[ -n "$KEEP_MACHINE" ]]; then
    echo "  - dedicated machine '${_MACHINE_NAME}' containers (machine itself KEPT per --keep-machine)"
  else
    echo "  - dedicated Podman machine/instance '${_MACHINE_NAME}' (pass --keep-machine to preserve)"
  fi
fi
if [[ -n "$PURGE_AUTH" ]]; then
  echo "  - transport state under ${DATA_DIR}, including the ga-kiro-auth file (--purge-auth given — next install needs a fresh login)"
else
  echo "  - transport state under ${DATA_DIR} (${DATA_DIR}/ga-kiro-auth is KEPT — pass --purge-auth to remove it)"
fi
echo ""
echo "Left alone (shared with other Podman workloads on this machine):"
echo "  - podman itself, podman-restart.service, podman.socket"
if [[ -z "$_HAS_DEDICATED_MACHINE" ]]; then
  echo "  - the podman machine VM (macOS)"
fi
echo "  - the ghcr.io/kirodotdev/kirocrew:stable base image"
echo ""

if [[ -z "$YES" ]]; then
  read -rp "Proceed? [y/N] " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { echo "Aborted."; exit 0; }
fi

# ── Crews ─────────────────────────────────────────────────────────────────────
# gs-* is per-crew ghostship resources only — ga-transport/ga-net use the
# separate ga- prefix, so this filter can never touch them.
# On macOS with a dedicated machine, target that machine's connection.

if [[ -n "$_HAS_DEDICATED_MACHINE" && "$OS" == "Darwin" ]]; then
  _PODMAN_CMD="podman --connection ${_MACHINE_NAME}"
  # podman-compose shells out to an external provider as a separate process,
  # so --connection on ${_PODMAN_CMD} above is NOT inherited by its internal
  # podman calls — only env vars are. Used below for the one compose call.
  _COMPOSE_ENV="CONTAINER_CONNECTION=${_MACHINE_NAME}"
elif [[ -n "$_HAS_DEDICATED_MACHINE" && "$OS" == "Linux" ]]; then
  # Target the dedicated storage root so containers, networks, and images in
  # it are actually found. Mirror install.sh's _PODMAN_CMD construction and
  # include CONTAINERS_CONF so the same scoped config applies (needed on WSL2).
  _GA_CONTAINERS_CONF="${HOME}/.config/${_MACHINE_NAME}/containers.conf"
  _STORAGE_ROOT_EARLY="${HOME}/.local/share/${_MACHINE_NAME}/containers/storage"
  _RUNTIME_DIR_EARLY="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  _PODMAN_CMD="env CONTAINERS_CONF=${_GA_CONTAINERS_CONF} podman --root=${_STORAGE_ROOT_EARLY} --runroot=${_RUNTIME_DIR_EARLY}/${_MACHINE_NAME}-containers"
  # Same reasoning as the Darwin branch above — --root/--runroot are flags on
  # ${_PODMAN_CMD}, not env vars, so they don't reach podman-compose's internal
  # calls either. CONTAINER_HOST (the raw dedicated socket) does.
  _COMPOSE_ENV="CONTAINER_HOST=unix://${_RUNTIME_DIR_EARLY}/${_MACHINE_NAME}/podman.sock"
else
  _PODMAN_CMD="podman"
  _COMPOSE_ENV=""
fi

echo ""
echo "Removing crew containers + volumes..."
for c in $(${_PODMAN_CMD} ps -a --filter name=^gs- --format '{{.Names}}' 2>/dev/null); do
  ${_PODMAN_CMD} rm -f "$c" >/dev/null 2>&1 && echo "  removed container: $c"
done
for v in $(${_PODMAN_CMD} volume ls --filter name=gs-vol- --format '{{.Name}}' 2>/dev/null); do
  ${_PODMAN_CMD} volume rm -f "$v" >/dev/null 2>&1 && echo "  removed volume: $v"
done
for v in $(${_PODMAN_CMD} volume ls --filter name=gs-home- --format '{{.Name}}' 2>/dev/null); do
  ${_PODMAN_CMD} volume rm -f "$v" >/dev/null 2>&1 && echo "  removed volume: $v"
done

# ── Transport ─────────────────────────────────────────────────────────────────

_COMPOSE_FILE="${XDG_DATA_HOME:-${HOME}/.local/share}/${_MACHINE_NAME}/data/compose.yml"
if [[ "$OS" == "Darwin" ]]; then
  _COMPOSE_FILE="${HOME}/Library/Application Support/${_MACHINE_NAME}/data/compose.yml"
fi
if [[ -f "$_COMPOSE_FILE" ]]; then
  eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${_COMPOSE_FILE}\" down" 2>/dev/null \
    && echo "✓ ga-transport stopped and removed via compose" || true
else
  ${_PODMAN_CMD} rm -f ga-transport >/dev/null 2>&1 && echo "✓ ga-transport container removed" || echo "  (ga-transport was not running)"
fi
${_PODMAN_CMD} network rm ga-net >/dev/null 2>&1 && echo "✓ ga-net network removed" || echo "  (ga-net did not exist)"

# ── Images ────────────────────────────────────────────────────────────────────

${_PODMAN_CMD} rmi -f localhost/kirocrew-crew:latest >/dev/null 2>&1 && echo "✓ localhost/kirocrew-crew:latest removed" || true
${_PODMAN_CMD} rmi -f localhost/transport:latest >/dev/null 2>&1 && echo "✓ localhost/transport:latest removed" || true

# ── Dedicated machine/instance teardown ───────────────────────────────────────

if [[ -n "$_HAS_DEDICATED_MACHINE" ]]; then
  echo ""
  echo "Removing dedicated Podman machine/instance '${_MACHINE_NAME}'..."

  if [[ "$OS" == "Darwin" ]]; then
    # macOS: stop and remove the dedicated podman machine
    if [[ -z "$KEEP_MACHINE" ]]; then
      podman machine stop "${_MACHINE_NAME}" 2>/dev/null && echo "  ✓ machine '${_MACHINE_NAME}' stopped" || true
      podman machine rm -f "${_MACHINE_NAME}" 2>/dev/null && echo "  ✓ machine '${_MACHINE_NAME}' removed" || true
    else
      echo "  (keeping machine '${_MACHINE_NAME}' per --keep-machine)"
    fi
  else
    # Linux: disable and remove dedicated systemd units, optionally remove storage
    _UNIT_DIR="${HOME}/.config/systemd/user"
    _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    _STORAGE_ROOT="${HOME}/.local/share/${_MACHINE_NAME}/containers/storage"

    # Stop and disable the socket and service
    systemctl --user disable --now "podman-${_MACHINE_NAME}.socket" 2>/dev/null \
      && echo "  ✓ podman-${_MACHINE_NAME}.socket disabled" || true
    systemctl --user disable --now "podman-${_MACHINE_NAME}.service" 2>/dev/null \
      && echo "  ✓ podman-${_MACHINE_NAME}.service disabled" || true

    # Remove unit files
    rm -f "${_UNIT_DIR}/podman-${_MACHINE_NAME}.socket" \
      && echo "  ✓ removed ${_UNIT_DIR}/podman-${_MACHINE_NAME}.socket" || true
    rm -f "${_UNIT_DIR}/podman-${_MACHINE_NAME}.service" \
      && echo "  ✓ removed ${_UNIT_DIR}/podman-${_MACHINE_NAME}.service" || true
    systemctl --user daemon-reload 2>/dev/null || true

    # Remove dedicated storage root
    if [[ -z "$KEEP_MACHINE" ]]; then
      if [[ -d "${_STORAGE_ROOT}" ]]; then
        # Overlay layer diffs are owned by subuid-mapped UIDs inside the
        # rootless user namespace — plain rm fails with "Permission denied".
        # Use podman unshare to enter the namespace and wipe them first, then
        # remove the rest as the host user.
        # Only wipe containers/ — not the entire ~/.local/share/${_MACHINE_NAME}
        # tree. The data/ subdirectory (which contains ga-kiro-auth) is handled
        # by the data-dir cleanup step below, which correctly respects
        # --purge-auth. Wiping the whole tree here would destroy ga-kiro-auth
        # even without --purge-auth.
        podman unshare rm -rf "${HOME}/.local/share/${_MACHINE_NAME}/containers/storage/overlay" \
          2>/dev/null || true
        rm -rf "${HOME}/.local/share/${_MACHINE_NAME}/containers"
        echo "  ✓ removed dedicated storage root: ${HOME}/.local/share/${_MACHINE_NAME}/containers"
      fi
      # Kill any stale rootlessport processes that were bound to this instance.
      # These survive container removal and hold the port open, blocking reinstall.
      # They are identified by having the ghostship working directory in their env.
      for pid in $(pgrep -x rootlessport 2>/dev/null); do
        port_env=$(cat /proc/"$pid"/environ 2>/dev/null | tr '\0' '\n' | grep -c "ghostship\|ghost.academy\|ghost_academy" || true)
        if [[ "$port_env" -gt 0 ]] || cat /proc/"$pid"/environ 2>/dev/null | tr '\0' '\n' | grep -q "GHOSTSHIP\|ghost-academy"; then
          kill "$pid" 2>/dev/null && echo "  ✓ killed stale rootlessport pid $pid" || true
        fi
      done
      # Also remove lingering runtime socket dirs for this instance
      rm -rf "${_RUNTIME_DIR}/${_MACHINE_NAME}-containers" 2>/dev/null || true
      rm -f "${_RUNTIME_DIR}/podman/${_MACHINE_NAME}.sock" 2>/dev/null || true
      rm -rf "${_RUNTIME_DIR}/${_MACHINE_NAME}" 2>/dev/null || true
      # Clean up ghostship-scoped containers.conf
      _GA_CONTAINERS_CONF_CLEANUP="${HOME}/.config/${_MACHINE_NAME}/containers.conf"
      if [[ -f "${_GA_CONTAINERS_CONF_CLEANUP}" ]]; then
        rm -f "${_GA_CONTAINERS_CONF_CLEANUP}"
        echo "  ✓ removed ${_GA_CONTAINERS_CONF_CLEANUP}"
        rmdir "$(dirname "${_GA_CONTAINERS_CONF_CLEANUP}")" 2>/dev/null || true
      fi
    else
      echo "  (keeping storage at ${_STORAGE_ROOT} per --keep-machine)"
    fi
  fi
fi

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
