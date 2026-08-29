#!/usr/bin/env bash
# Start Ghost Academy — bring up the Podman service and the ga-transport
# container. Safe to run any time. Does nothing if already running.
# Requires install.sh to have been run first.
#
# Usage:
#   ./start.sh [--config <path>] [--machine-name <name>]
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"
_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# ── Flag parsing ──────────────────────────────────────────────────────────────
_CONFIG_FLAG=""
_MACHINE_FLAG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)       _CONFIG_FLAG="$2"; shift 2 ;;
    --machine-name) _MACHINE_FLAG="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Config discovery ──────────────────────────────────────────────────────────
_load_config() {
  local cfg="$1"
  if [[ ! -f "$cfg" ]]; then
    echo "Config file not found: $cfg" >&2; exit 1
  fi
  # shellcheck source=/dev/null
  source "$cfg"
  echo "✓ Using config: $cfg"
}

if [[ -n "$_CONFIG_FLAG" ]]; then
  _load_config "$_CONFIG_FLAG"
else
  # Scan candidate locations in preference order; use first match.
  # Repo-adjacent configs take priority; ~/.ghostship is the persistent fallback.
  _CANDIDATES=()
  for _f in \
    "${GHOSTSHIP_DIR}/ghostship.conf" \
    "${GHOSTSHIP_DIR}/config/ghostship.conf" \
    "${HOME}/.ghostship/ghostship.conf"
  do
    [[ -f "$_f" ]] && _CANDIDATES+=("$_f") || true
  done

  # Deduplicate by real path
  declare -A _seen=()
  _UNIQUE=()
  for _f in "${_CANDIDATES[@]}"; do
    _real="$(realpath "$_f" 2>/dev/null || echo "$_f")"
    if [[ -z "${_seen[$_real]:-}" ]]; then
      _seen["$_real"]=1
      _UNIQUE+=("$_f")
    fi
  done

  if [[ ${#_UNIQUE[@]} -eq 0 ]]; then
    if [[ -t 0 ]]; then
      echo "No ghostship.conf found in:"
      echo "  ${GHOSTSHIP_DIR}/ghostship.conf"
      echo "  ${GHOSTSHIP_DIR}/config/ghostship.conf"
      echo "  ${HOME}/.ghostship/ghostship.conf"
      echo ""
      read -rp "Path to config (blank = use defaults): " _CONFIG_FLAG
      [[ -n "$_CONFIG_FLAG" ]] && _load_config "$_CONFIG_FLAG" || echo "  (using built-in defaults)"
    else
      echo "No ghostship.conf found — using built-in defaults"
    fi
  elif [[ ${#_UNIQUE[@]} -eq 1 ]]; then
    _load_config "${_UNIQUE[0]}"
  else
    echo "Multiple ghostship configs found:"
    for i in "${!_UNIQUE[@]}"; do
      echo "  $((i+1))) ${_UNIQUE[$i]}"
    done
    if [[ -t 0 ]]; then
      read -rp "Choose [1-${#_UNIQUE[@]}] or enter a path: " _choice
      if [[ "$_choice" =~ ^[0-9]+$ ]] && (( _choice >= 1 && _choice <= ${#_UNIQUE[@]} )); then
        _load_config "${_UNIQUE[$((_choice-1))]}"
      elif [[ -n "$_choice" ]]; then
        _load_config "$_choice"
      else
        _load_config "${_UNIQUE[0]}"
      fi
    else
      _load_config "${_UNIQUE[0]}"
    fi
  fi
fi

# ── Apply flag overrides ──────────────────────────────────────────────────────
[[ -n "$_MACHINE_FLAG" ]] && GA_MACHINE_NAME="$_MACHINE_FLAG" || true

GA_MACHINE_NAME="${GA_MACHINE_NAME:-ghost-academy}"
GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE:-true}"
PORT="${PORT:-64057}"

# ── 1. Ensure the Podman service / machine is running ────────────────────────

if [[ "$OS" == "Darwin" ]]; then
  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    if ! podman machine inspect "${GA_MACHINE_NAME}" --format '{{.State}}' 2>/dev/null | grep -qi "running"; then
      echo "Starting podman machine '${GA_MACHINE_NAME}'..."
      podman machine start "${GA_MACHINE_NAME}"
    else
      echo "✓ Podman machine '${GA_MACHINE_NAME}' already running"
    fi
    _PODMAN_CMD="podman --connection ${GA_MACHINE_NAME}"
  else
    if ! podman machine list --format '{{.Running}}' 2>/dev/null | grep -q true; then
      echo "Starting podman machine..."
      podman machine start
    else
      echo "✓ Podman machine already running"
    fi
    _PODMAN_CMD="podman"
  fi
else
  # Linux (systemd or otherwise)
  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    PODMAN_SOCK="${_RUNTIME_DIR}/${GA_MACHINE_NAME}/podman.sock"
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      if command -v systemctl >/dev/null 2>&1 && systemctl --user is-system-running >/dev/null 2>&1; then
        echo "Starting podman-${GA_MACHINE_NAME}.service..."
        systemctl --user start "podman-${GA_MACHINE_NAME}.service"
      else
        echo "Starting dedicated Podman service for '${GA_MACHINE_NAME}'..."
        _STORAGE_ROOT="${HOME}/.local/share/${GA_MACHINE_NAME}/containers/storage"
        _RUNROOT="${_RUNTIME_DIR}/${GA_MACHINE_NAME}-containers"
        _GA_CONTAINERS_CONF="${HOME}/.config/${GA_MACHINE_NAME}/containers.conf"
        mkdir -p "$(dirname "$PODMAN_SOCK")"
        nohup env CONTAINERS_CONF="${_GA_CONTAINERS_CONF}" \
          podman --root="${_STORAGE_ROOT}" --runroot="${_RUNROOT}" \
          system service --time=0 "unix://${PODMAN_SOCK}" \
          >"/tmp/ghostship-podman-${GA_MACHINE_NAME}.log" 2>&1 &
      fi
      for i in $(seq 1 15); do [[ -S "$PODMAN_SOCK" ]] && break; sleep 1; done
      if [[ ! -S "$PODMAN_SOCK" ]]; then
        echo "✗ Podman socket did not appear at ${PODMAN_SOCK}" >&2; exit 1
      fi
      echo "✓ Podman service started"
    else
      echo "✓ Podman socket already present"
    fi
  else
    PODMAN_SOCK="${PODMAN_SOCK:-/run/user/$(id -u)/podman/podman.sock}"
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      if command -v systemctl >/dev/null 2>&1; then
        systemctl --user start podman.socket 2>/dev/null || true
      else
        nohup podman system service --time=0 "unix://${PODMAN_SOCK}" \
          >/tmp/ghostship-podman.log 2>&1 &
      fi
      for i in $(seq 1 10); do [[ -S "$PODMAN_SOCK" ]] && break; sleep 1; done
    fi
    echo "✓ Podman socket ready"
  fi
  _PODMAN_CMD="CONTAINER_HOST=unix://${PODMAN_SOCK} podman"
fi

# ── 2. Start ga-transport via compose ────────────────────────────────────────

# DATA_DIR is where compose.yml was written by install.sh
_DATA_DIR="${XDG_DATA_HOME:-${HOME}/.local/share}/${GA_MACHINE_NAME}/data"
if [[ "$OS" == "Darwin" ]]; then
  _DATA_DIR="${HOME}/Library/Application Support/${GA_MACHINE_NAME}/data"
fi
_COMPOSE_FILE="${_DATA_DIR}/compose.yml"

if [[ ! -f "$_COMPOSE_FILE" ]]; then
  echo "✗ compose.yml not found at ${_COMPOSE_FILE}" >&2
  echo "  Run ./install.sh first to generate it." >&2
  exit 1
fi

echo "Starting ga-transport via compose..."
# podman-compose shells out to an external provider as a separate process, so
# flags on the outer `podman compose` invocation aren't inherited by its
# internal podman calls — only env vars cross that boundary. Point it at the
# right instance via CONTAINER_HOST on Linux, or CONTAINER_CONNECTION on a
# dedicated macOS machine (bare `podman` would otherwise resolve via whatever
# the ambient default connection happens to be, which may not be
# '${GA_MACHINE_NAME}').
if [[ "$OS" == "Linux" && -n "${PODMAN_SOCK:-}" ]]; then
  _COMPOSE_ENV="CONTAINER_HOST=unix://${PODMAN_SOCK}"
elif [[ "$OS" == "Darwin" && "${GA_DEDICATED_MACHINE}" == "true" ]]; then
  _COMPOSE_ENV="CONTAINER_CONNECTION=${GA_MACHINE_NAME}"
else
  _COMPOSE_ENV=""
fi
eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${_COMPOSE_FILE}\" up -d"

_ready=0
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    _ready=1; break
  fi
  sleep 1
done

if [[ "$_ready" == "1" ]]; then
  echo "✓ ga-transport is ready (http://127.0.0.1:${PORT}/health)"
else
  echo "✗ ga-transport did not become ready within 30s" >&2
  eval "${_PODMAN_CMD} logs ga-transport --tail 10" >&2
  exit 1
fi
