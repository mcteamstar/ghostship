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

# ── Python / YAML config resolution (TRN-253) ────────────────────────────────
# start.sh needs only three config vars: GA_MACHINE_NAME, GA_DEDICATED_MACHINE,
# PORT. Resolve them the same way install.sh does — via yaml_config.py in a
# PyYAML is vendored at bin/lib/vendor/yaml — no venv, no pip, no network needed.

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to parse the YAML config." >&2; exit 1
fi

_YAML_CONFIG_HELPER="${GHOSTSHIP_DIR}/bin/lib/yaml_config.py"

_REPO_YAML="${GHOSTSHIP_DIR}/config/ghostship.yaml"
if [[ "$OS" == "Darwin" ]]; then
  _XDG_YAML="${HOME}/Library/Application Support/ghost-academy/ghostship.yaml"
else
  _XDG_YAML="${XDG_CONFIG_HOME:-${HOME}/.config}/ghost-academy/ghostship.yaml"
fi

if [[ -n "$_CONFIG_FLAG" ]]; then
  _RESOLVED="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER" resolve --config "$_CONFIG_FLAG")" || {
    echo "Error: failed to parse config file: $_CONFIG_FLAG" >&2; exit 1
  }
else
  _RESOLVED="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER" resolve --repo "$_REPO_YAML" --xdg "$_XDG_YAML")" || {
    echo "Error: failed to resolve YAML config." >&2; exit 1
  }
fi
eval "$_RESOLVED"

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
# Pin the compose provider to podman-compose so Podman cannot select docker-compose
# when both are installed (Podman's default precedence prefers docker-compose).
_COMPOSE_ENV="${_COMPOSE_ENV:+${_COMPOSE_ENV} }PODMAN_COMPOSE_PROVIDER=$(command -v podman-compose 2>/dev/null || true)"
eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${_COMPOSE_FILE}\" up -d"

# Probe /health through ga-portal at the address install.sh published it on
# (GA_PORTAL_HOST in compose.yml) — the path every client uses.
# shellcheck source=lib/portal_host.sh
source "${GHOSTSHIP_DIR}/bin/lib/portal_host.sh"
_PORTAL_HOST="$(sed -n 's/^ *GA_PORTAL_HOST: "\(.*\)"$/\1/p' "${_COMPOSE_FILE}" | head -n 1)"
_PORTAL_TLS="$(sed -n 's/^ *GA_PORTAL_TLS_MODE: "\(.*\)"$/\1/p' "${_COMPOSE_FILE}" | head -n 1)"
_scheme="http"
[[ -n "$_PORTAL_TLS" && "$_PORTAL_TLS" != "off" ]] && _scheme="https"
_probe_url="$(portal_probe_base "${_PORTAL_HOST:-127.0.0.1}" "${PORT}" "$_scheme")/health"

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
