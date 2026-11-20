#!/usr/bin/env bash
# Disposable Linux install/start smoke test. All Podman state lives under a
# unique temporary HOME and is served through a private temporary API socket.
set -Ee -o pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SMOKE_TMP_BASE="$RUNNER_TEMP"
if [[ -z "$SMOKE_TMP_BASE" ]]; then
  SMOKE_TMP_BASE="/tmp"
fi
SMOKE_ROOT="$(mktemp -d "$SMOKE_TMP_BASE/ghostship-install-smoke.XXXXXXXX")"
SMOKE_HOME="$SMOKE_ROOT/home"
SMOKE_BIN="$SMOKE_ROOT/bin"
SMOKE_RUNTIME="$SMOKE_ROOT/runtime"
SMOKE_DATA="$SMOKE_ROOT/data"
SMOKE_CONFIG="$SMOKE_ROOT/ghostship.yaml"
PODMAN_SERVICE_PID=""
cleanup_early() {
  local status=$?
  trap - EXIT
  set +e
  rm -rf -- "$SMOKE_ROOT"
  exit "$status"
}
trap cleanup_early EXIT
if [[ -z "$GITHUB_RUN_ID" ]]; then
  GITHUB_RUN_ID="local"
fi
if [[ -z "$GITHUB_RUN_ATTEMPT" ]]; then
  GITHUB_RUN_ATTEMPT="1"
fi
MACHINE_NAME="ghostship-smoke-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$$"

mkdir -p "$SMOKE_HOME" "$SMOKE_BIN" "$SMOKE_RUNTIME" "$SMOKE_DATA"
chmod 700 "$SMOKE_RUNTIME"
export HOME="$SMOKE_HOME"
export XDG_CONFIG_HOME="$SMOKE_HOME/.config"
export XDG_DATA_HOME="$SMOKE_DATA"
export XDG_RUNTIME_DIR="$SMOKE_RUNTIME"
export PODMAN_SOCK="$SMOKE_RUNTIME/podman.sock"
unset CONTAINER_HOST CONTAINER_CONNECTION
mkdir -p "$XDG_CONFIG_HOME/containers"
export CONTAINERS_CONF="$XDG_CONFIG_HOME/containers/containers.conf"
printf '[engine]\ncgroup_manager = "cgroupfs"\n[network]\ndefault_rootless_network_cmd = "slirp4netns"\n' > "$CONTAINERS_CONF"
export GA_MACHINE_NAME="$MACHINE_NAME"
export GA_DEDICATED_MACHINE="false"
export PATH="$SMOKE_BIN:$PATH"

# install.sh probes systemd for optional socket setup. The smoke test starts
# its own Podman API service and keeps those optional calls inside this job.
for command_name in systemctl loginctl; do
  cat > "$SMOKE_BIN/$command_name" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
  chmod 755 "$SMOKE_BIN/$command_name"
done

read -r PORT DASHBOARD_PORT < <(
  python3 -c 'import socket; a=socket.socket(); b=socket.socket(); a.bind(("127.0.0.1", 0)); b.bind(("127.0.0.1", 0)); print(a.getsockname()[1], b.getsockname()[1]); a.close(); b.close()'
)
HEALTH_URL="http://127.0.0.1:$PORT/health"
SMOKE_DATA_DIR="$XDG_DATA_HOME/$MACHINE_NAME/data"

cat > "$SMOKE_CONFIG" <<EOF
network:
  host: 127.0.0.1
  port: "$PORT"
  api_key: false
machine:
  dedicated: false
  name: "$MACHINE_NAME"
portal:
  tls_mode: "off"
  dashboard:
    port_range:
      start: "$DASHBOARD_PORT"
      size: 1
backends:
  default: kiro
EOF

cleanup_resources() {
  if podman info >/dev/null 2>&1; then
    if [[ -f "$SMOKE_DATA_DIR/compose.yml" ]]; then
      podman-compose --project-name ga -f "$SMOKE_DATA_DIR/compose.yml" \
        down --volumes --remove-orphans >/dev/null 2>&1 || true
    fi
    podman rm -f ga-transport ga-portal ga-radar >/dev/null 2>&1 || true
    podman network rm ga-portside >/dev/null 2>&1 || true
    podman network rm ga-starboard >/dev/null 2>&1 || true
    podman secret rm ga-transport-secret >/dev/null 2>&1 || true
    podman secret rm ga-api-key >/dev/null 2>&1 || true
    podman volume rm -f ga_ga-portal-data >/dev/null 2>&1 || true
    podman volume rm -f ga-portal-data >/dev/null 2>&1 || true
  fi
}

assert_resources_clean() {
  local names
  names="$(podman ps -a --format '{{.Names}}')"
  for resource in ga-transport ga-portal ga-radar; do
    if grep -Fxq "$resource" <<<"$names"; then
      echo "Smoke container remains after cleanup: $resource" >&2
      return 1
    fi
  done
  for resource in ga-portside ga-starboard; do
    if podman network inspect "$resource" >/dev/null 2>&1; then
      echo "Smoke network remains after cleanup: $resource" >&2
      return 1
    fi
  done
  for resource in ga-transport-secret ga-api-key; do
    if podman secret inspect "$resource" >/dev/null 2>&1; then
      echo "Smoke secret remains after cleanup: $resource" >&2
      return 1
    fi
  done
  for resource in ga_ga-portal-data ga-portal-data; do
    if podman volume inspect "$resource" >/dev/null 2>&1; then
      echo "Smoke volume remains after cleanup: $resource" >&2
      return 1
    fi
  done
}

pass_exit() {
  local status=$?
  trap - EXIT
  cleanup_resources
  exit "$status"
}

cleanup_job() {
  local status=$?
  trap - EXIT
  set +e
  cleanup_resources
  if [[ -n "$PODMAN_SERVICE_PID" ]]; then
    kill "$PODMAN_SERVICE_PID" 2>/dev/null || true
    wait "$PODMAN_SERVICE_PID" 2>/dev/null || true
  fi
  podman --remote=false unshare rm -rf -- "$SMOKE_ROOT" || rm -rf -- "$SMOKE_ROOT"
  exit "$status"
}
trap cleanup_job EXIT

podman --remote=false system service --time=0 "unix://$PODMAN_SOCK" \
  > "$SMOKE_ROOT/podman-service.log" 2>&1 &
PODMAN_SERVICE_PID=$!
for attempt in {1..30}; do
  if [[ -S "$PODMAN_SOCK" ]]; then
    break
  fi
  sleep 1
done
if [[ ! -S "$PODMAN_SOCK" ]]; then
  cat "$SMOKE_ROOT/podman-service.log"
  echo "Temporary Podman API socket did not become ready" >&2
  exit 1
fi
podman info >/dev/null

run_smoke_pass() (
  local mode="$1"
  trap pass_exit EXIT
  cd "$REPO_DIR"
  echo "Installing Ghostship ($mode)"
  PYTHONUNBUFFERED=1 ./install.sh --config "$SMOKE_CONFIG"
  echo "Starting Ghostship ($mode)"
  ./bin/start.sh --config "$SMOKE_CONFIG"
  curl --fail --silent --show-error --max-time 15 "$HEALTH_URL" >/dev/null
  echo "Portal /health is ready at $HEALTH_URL"
  if [[ "$mode" == "forced-failure" ]]; then
    podman stop ga-transport >/dev/null
    if curl --fail --silent --show-error --max-time 15 "$HEALTH_URL" >/dev/null 2>&1; then
      echo "Expected portal /health to fail after stopping ga-transport" >&2
      exit 98
    fi
    echo "Portal /health failure after stopping ga-transport was detected"
    exit 73
  fi
)

run_smoke_pass success
assert_resources_clean
echo "Cleanup after successful readiness: PASS"

if run_smoke_pass forced-failure; then
  echo "Forced-failure smoke pass unexpectedly succeeded" >&2
  exit 1
else
  pass_status=$?
  if [[ "$pass_status" -ne 73 ]]; then
    echo "Forced-failure smoke pass returned $pass_status instead of 73" >&2
    exit 1
  fi
fi
assert_resources_clean
echo "Cleanup after forced portal-to-transport failure: PASS"
