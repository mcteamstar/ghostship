#!/usr/bin/env bash
# Start Ghost Academy — bring up the Podman service and the ga-transport
# container. Safe to run any time. Does nothing if already running.
# Requires install.sh to have been run first.
#
# Usage:
#   ./start.sh [--config <path>] [--machine-name <name>]
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

# ── Python / YAML config resolution (via start_ops.py — no eval of subprocess) ──
if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to parse the YAML config." >&2; exit 1
fi

_start_ops_args=("--ghostship-dir" "${GHOSTSHIP_DIR}")
[[ -n "$_CONFIG_FLAG" ]] && _start_ops_args+=("--config" "$_CONFIG_FLAG")

_start_ops_out="$(
  PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" \
  python3 "${GHOSTSHIP_DIR}/bin/lib/start_ops.py" "${_start_ops_args[@]}"
)" || { echo "Error: failed to resolve YAML config." >&2; exit 1; }

# Parse the KEY=value lines (values are simple identifiers/ports; no quotes needed)
_parse_start_ops() {
  local line key val
  while IFS= read -r line; do
    key="${line%%=*}"
    val="${line#*=}"
    case "$key" in
      GA_MACHINE_NAME|GA_DEDICATED_MACHINE|PORT|HOST|GA_PORTAL_TLS_MODE)
        printf -v "$key" '%s' "$val" ;;
    esac
  done <<< "$_start_ops_out"
}
_parse_start_ops

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
  # Linux
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
if [[ "$OS" == "Linux" && -n "${PODMAN_SOCK:-}" ]]; then
  _COMPOSE_ENV="CONTAINER_HOST=unix://${PODMAN_SOCK}"
elif [[ "$OS" == "Darwin" && "${GA_DEDICATED_MACHINE}" == "true" ]]; then
  _COMPOSE_ENV="CONTAINER_CONNECTION=${GA_MACHINE_NAME}"
else
  _COMPOSE_ENV=""
fi
_PODMAN_COMPOSE_BIN="$(command -v podman-compose 2>/dev/null || true)"
_COMPOSE_ENV="${_COMPOSE_ENV:+${_COMPOSE_ENV} }PODMAN_COMPOSE_PROVIDER=${_PODMAN_COMPOSE_BIN}"
eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${_COMPOSE_FILE}\" up -d"

# ── 3. Health check through ga-portal ────────────────────────────────────────
GA_PORTAL_HOST="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "${GHOSTSHIP_DIR}/bin/lib/portal_host.py" addr "${HOST:-127.0.0.1}")"
_PORTAL_TLS="${GA_PORTAL_TLS_MODE:-off}"
_scheme="http"
[[ -n "$_PORTAL_TLS" && "$_PORTAL_TLS" != "off" ]] && _scheme="https"
_probe_url="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "${GHOSTSHIP_DIR}/bin/lib/portal_host.py" probe_base "${HOST:-127.0.0.1}" "${PORT}" "$_scheme")/health"

_ready=0
for i in $(seq 1 30); do
  if curl -sfk "$_probe_url" >/dev/null 2>&1; then
    _ready=1; break
  fi
  sleep 1
done

if [[ "$_ready" == "1" ]]; then
  echo "✓ ga-transport is ready (${_probe_url})"
else
  echo "✗ ga-transport did not become ready through ga-portal within 30s (${_probe_url})" >&2
  eval "${_PODMAN_CMD} logs ga-transport --tail 10" >&2
  eval "${_PODMAN_CMD} logs ga-portal --tail 10" >&2
  exit 1
fi
