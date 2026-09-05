#!/usr/bin/env bash
# Install/update Ghost Academy locally on macOS or Linux.
#
# Builds the crew + transport images and runs the transport container
# directly with `podman run`, bound to localhost — no remote host, no
# reverse proxy, just this machine. On macOS, Podman runs inside a
# lightweight Linux VM ("podman machine"); on Linux it runs directly on
# the host kernel, no VM involved.
#
# Run:
#   ./install.sh [--config <path>] [--identity-provider <url>] \
#                [--region <region>] [--license <license>] [--port <port>] \
#                [--model <model>] [--api-key <key>]
#
# Config file: copy config/ghostship.conf.example to ghostship.conf and pass
#   ./install.sh --config ghostship.conf
# to persist settings across reinstalls. See docs/configuration.md.
#
# After a fresh install, register the MCP server and call launch:
#   kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
#   (from Kiro CLI) ghostship__launch(crew_id="general")
#
# Identity provider config: kiro-cli login needs to know which identity
# provider/region to authenticate against — without it, it falls back to
# Builder ID (free tier), which is likely not what an org-licensed kiro-cli
# install should use. Resolved in this order:
#   1. --config <path>   — a shell file exporting KIRO_IDENTITY_PROVIDER,
#                           KIRO_REGION, KIRO_LICENSE
#   2. --identity-provider / --region / --license flags
#   3. Interactive prompt, if running in a terminal and still unset
#
# Port: MCP and file transfer both listen on --port (default 64057) — one port
# serves all routes, matching server.py's unified app.
#
# API key: --api-key <key> enables MCP bearer-token auth and persists the
# key to your data directory, so it stays enabled on future installs without
# repeating the flag. --api-key "" (empty) clears it. See docs/auth.md.
# set -e: exit on any command failure. set -o pipefail: exit on failures
# within pipelines. Together these ensure that podman machine ssh failures
# (including those in command-substitution subshells like GUEST_UID=...)
# propagate as non-zero exits. Explicit error guards below add diagnostic
# messages to name *what* failed.
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"

# ── Built-in defaults (literal assignments, BEFORE config sourcing) ──────────
# Resolution order: built-in default → config file → CLI flag.
# A literal assignment here ensures an ambient env var from the invoking shell
# is unconditionally overwritten — only the config file or a flag can override.
PORT=64057
KIRO_IDENTITY_PROVIDER=""
KIRO_REGION=""
KIRO_LICENSE=""
KC_MODEL_OVERRIDE=""
KC_MODEL_DEFAULT=""
GA_HOST_URL=""
GA_API_KEY=""
GA_DEDICATED_MACHINE=true
GA_MACHINE_CPUS=8
GA_MACHINE_MEMORY=16384
GA_MACHINE_DISK=100
GA_MACHINE_NAME=ghost-academy
GA_MAX_CREWS=20
GA_MAX_ACTIVE_CREWS=3
GA_IDLE_TIMEOUT_SECS=300
GA_SUBAGENT_TIMEOUT_SECS=3600
GA_SUBAGENT_MAX_TURNS=200
GA_CREW_AGENT=kiro
GA_MIN_FREE_MEM_GB=2.0
GA_SPAWN_MIN_MEMORY_GB=1.5
GA_RESOURCE_PRESSURE_GB=2.0
GA_RESOURCE_CRITICAL_GB=1.0
GA_GIT_AUTHOR_NAME=""
GA_GIT_AUTHOR_EMAIL=""
GA_DASHBOARD_PORT_RANGE_START=64058
GA_DASHBOARD_PORT_RANGE_SIZE=50
GA_DASHBOARD_PORT_ENABLED=true
# ── Caddy reverse proxy (TRN-92 / TRN-103) ───────────────────────────────────
# ga-portal (Caddy) is always installed; there is no opt-out.
# Caddy listens on PORT (same port as the transport, resolved above).
# Default: plain HTTP on 64057 — zero-config installs work at
# http://localhost:64057/mcp with no TLS setup required.
# To enable TLS: set GA_PORTAL_TLS_MODE=acme + GA_PORTAL_DOMAIN (any port).
GA_PORTAL_TLS_MODE=off
GA_PORTAL_DOMAIN=""

# ── Config file: extract --config <path> first (peek at $@, don't consume) ──
# Source BEFORE the flag-parsing loop so CLI flags override config-file values.
CONFIG_FILE=""
_args=("$@")
for ((i=0; i < ${#_args[@]}; i++)); do
  if [[ "${_args[i]}" == "--config" ]]; then
    CONFIG_FILE="${_args[i+1]:-}"
    break
  fi
done

if [[ -n "$CONFIG_FILE" ]]; then
  if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: config file does not exist: $CONFIG_FILE" >&2
    exit 1
  fi
  if [[ ! -r "$CONFIG_FILE" ]]; then
    echo "Error: config file is not readable: $CONFIG_FILE" >&2
    exit 1
  fi
  # Migration guard: GA_PORTAL_PORT was renamed to PORT in TRN-111.
  # If the config file sets GA_PORTAL_PORT, warn and substitute to PORT before sourcing.
  if grep -qE '^[[:space:]]*GA_PORTAL_PORT=' "$CONFIG_FILE" 2>/dev/null; then
    echo "⚠ Deprecated GA_PORTAL_PORT found in config — auto-migrating to PORT" >&2
    _MIGRATED_CONFIG="$(mktemp)"
    sed 's/^\([[:space:]]*\)GA_PORTAL_PORT=/\1PORT=/' "$CONFIG_FILE" > "$_MIGRATED_CONFIG"
    CONFIG_FILE="$_MIGRATED_CONFIG"
  fi
  # TRUST ASSUMPTION: this executes arbitrary shell code from the path the user
  # passed via --config. The caller is trusted — this is intentional: config
  # files export env vars that control identity provider, region, API keys, etc.
  # Do NOT source untrusted paths.
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  echo "✓ Sourced config file: $CONFIG_FILE"
else
  # Auto-detect config from standard locations (no --config flag passed).
  for _candidate in \
    "${GHOSTSHIP_DIR}/ghostship.conf" \
    "${GHOSTSHIP_DIR}/config/ghostship.conf"
  do
    if [[ -f "$_candidate" ]]; then
      # shellcheck source=/dev/null
      source "$_candidate"
      echo "✓ Sourced config file: $_candidate"
      break
    fi
  done
fi

# ── Flag parsing (runs AFTER config sourcing — flags override config) ────────
API_KEY_FLAG_PASSED=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) shift 2 ;;  # already consumed above
    --identity-provider) KIRO_IDENTITY_PROVIDER="$2"; shift 2 ;;
    --region) KIRO_REGION="$2"; shift 2 ;;
    --license) KIRO_LICENSE="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --model) KC_MODEL_OVERRIDE="$2"; shift 2 ;;
    --model-default) KC_MODEL_DEFAULT="$2"; shift 2 ;;
    --public-url) GA_HOST_URL="$2"; shift 2 ;;
    --api-key) GA_API_KEY="$2"; API_KEY_FLAG_PASSED=1; shift 2 ;;
    --caddy-domain) GA_PORTAL_DOMAIN="$2"; shift 2 ;;
    --caddy-tls-mode) GA_PORTAL_TLS_MODE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${KIRO_IDENTITY_PROVIDER:-}" && -t 0 ]]; then
  read -rp "kiro-cli identity provider URL (blank = default Builder ID login): " KIRO_IDENTITY_PROVIDER
fi
if [[ -n "${KIRO_IDENTITY_PROVIDER:-}" && -z "${KIRO_REGION:-}" && -t 0 ]]; then
  read -rp "AWS region for that identity provider: " KIRO_REGION
fi

# ── Podman ────────────────────────────────────────────────────────────────────

if ! command -v podman >/dev/null 2>&1; then
  echo "✗ podman not found." >&2
  echo "" >&2
  echo "Install podman >= 4.4 before running install.sh:" >&2
  case "$OS" in
    Darwin) echo "  brew install podman" >&2 ;;
    Linux)
      echo "  # Ubuntu/Debian:" >&2
      echo "  sudo apt-get install -y podman podman-compose" >&2
      echo "  # Fedora/RHEL:" >&2
      echo "  sudo dnf install -y podman podman-compose" >&2
      echo "  # Other distros: see docs/manual-install.md" >&2 ;;
  esac
  exit 1
fi

# ── Check prerequisites are installed ────────────────────────────────────────
# podman and podman-compose must be installed before running install.sh.
# See README.md and docs/manual-install.md for install commands.

# ── Verify podman compose is available ───────────────────────────────────────
# `podman compose` delegates to an external provider (podman-compose or
# docker-compose). Install it before running install.sh.
if ! command -v podman-compose >/dev/null 2>&1 && \
   ! (command -v docker-compose >/dev/null 2>&1) && \
   ! (command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1); then
  echo "✗ podman-compose not found." >&2
  echo "" >&2
  echo "Install podman-compose before running install.sh:" >&2
  case "$OS" in
    Darwin) echo "  brew install podman-compose" >&2 ;;
    Linux)
      echo "  # Ubuntu/Debian:" >&2
      echo "  sudo apt-get install -y podman-compose" >&2
      echo "  # Fedora/RHEL:" >&2
      echo "  sudo dnf install -y podman-compose" >&2 ;;
  esac
  exit 1
fi

# ── Podman runtime (machine VM on macOS, native on Linux) ───────────────────

if [[ "$OS" == "Darwin" ]]; then
  # macOS has no container-capable kernel of its own — podman runs inside a
  # Linux VM ("podman machine"). Linux needs none of this; see the else branch.

  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    # ── Dedicated machine provisioning (macOS) ──────────────────────────────
    # A separate podman machine exclusively for Ghost Academy, isolating crew
    # containers from the user's default machine. See design.md.
    _MACHINE="${GA_MACHINE_NAME}"

    if ! podman machine list --format '{{.Name}}' 2>/dev/null | grep -qw "${_MACHINE}"; then
      echo "Initialising dedicated podman machine '${_MACHINE}'..."
      podman machine init "${_MACHINE}" \
        --cpus "${GA_MACHINE_CPUS}" \
        --memory "${GA_MACHINE_MEMORY}" \
        --disk-size "${GA_MACHINE_DISK}"
    fi

    # Start the dedicated machine if not already running
    if ! podman machine inspect "${_MACHINE}" --format '{{.State}}' 2>/dev/null | grep -qi "running"; then
      echo "Starting dedicated podman machine '${_MACHINE}'..."
      podman machine start "${_MACHINE}"
    fi

    # Enable podman-restart.service inside the dedicated machine guest
    podman machine ssh "${_MACHINE}" -- systemctl --user enable podman-restart.service \
      || { echo "Error: failed to enable podman-restart.service in '${_MACHINE}' guest — is the VM running?" >&2; exit 1; }
    echo "✓ podman-restart.service enabled in dedicated machine '${_MACHINE}'"

    # Resolve the in-guest socket path for the dedicated machine
    GUEST_UID="$(podman machine ssh "${_MACHINE}" -- id -u)" \
      || { echo "Error: failed to retrieve guest UID from '${_MACHINE}' — SSH into the VM may be broken" >&2; exit 1; }
    PODMAN_SOCK="/run/user/${GUEST_UID}/podman/podman.sock"
    echo "✓ Dedicated machine '${_MACHINE}' guest socket: ${PODMAN_SOCK}"
  else
    # ── Default machine (macOS, existing behaviour) ──────────────────────────
    if ! podman machine list --format '{{.Name}}' 2>/dev/null | grep -q .; then
      echo "Initialising podman machine..."
      podman machine init --cpus 4 --memory 8192 --disk-size 60
    fi

    if ! podman machine list --format '{{.Running}}' 2>/dev/null | grep -q true; then
      echo "Starting podman machine..."
      podman machine start
    fi

    # podman-restart.service is disabled by default in the guest, so a container
    # run with --restart=always does NOT come back after `podman machine stop` +
    # `start` on its own (verified: it needs this unit enabled). This only
    # affects what happens once you start the machine yourself — it does not
    # make the machine start automatically (no launchd/login autostart is used
    # here on purpose).
    podman machine ssh -- systemctl --user enable podman-restart.service \
      || { echo "Error: failed to enable podman-restart.service in the podman machine guest — is the VM running?" >&2; exit 1; }
    echo "✓ podman-restart.service enabled (transport survives machine restarts)"

    # In-guest socket path (NOT the host-side /var/folders proxy socket from
    # `podman machine inspect` — that path only exists on macOS and can't be
    # bind-mounted into a container, which runs inside the guest VM). Confirmed
    # via `podman machine ssh -- systemctl --user status podman.socket`.
    GUEST_UID="$(podman machine ssh -- id -u)" \
      || { echo "Error: failed to retrieve guest UID via 'podman machine ssh -- id -u' — SSH into the VM may be broken" >&2; exit 1; }
    PODMAN_SOCK="/run/user/${GUEST_UID}/podman/podman.sock"
    echo "✓ Guest podman socket: ${PODMAN_SOCK}"
  fi

  DATA_DIR="$HOME/Library/Application Support/${GA_MACHINE_NAME}/data"

  # The podman-machine guest (Fedora CoreOS) runs SELinux enforcing. The socket
  # is labeled user_tmp_t, which the container's confined domain can't access —
  # bind-mounting it produces a silent "Permission denied" even though the DAC
  # owner/uid mapping (container root -> host uid, verified via
  # `podman exec transport cat /proc/self/uid_map`) lines up correctly. Fixed
  # below with `--security-opt label=disable` on the transport container.
else
  # Linux: podman runs directly on the host, no VM, no guest indirection.

  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    # ── Dedicated Podman instance (Linux) ────────────────────────────────────
    # A separate systemd socket-activated Podman service with its own storage
    # root, completely isolated from the default instance.
    _MACHINE="${GA_MACHINE_NAME}"
    _UNIT_DIR="${HOME}/.config/systemd/user"
    _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    _STORAGE_ROOT="${HOME}/.local/share/${_MACHINE}/containers/storage"

    mkdir -p "${_UNIT_DIR}"

    # Write the dedicated Podman service unit. We run podman system service
    # directly (Type=simple) so it creates the socket file itself — systemd
    # socket activation holds the fd internally without materialising the file,
    # which breaks the socket check on modern kernels (Ubuntu 25.10+).
    # RuntimeDirectory= ensures the socket dir exists under XDG_RUNTIME_DIR.
    cat > "${_UNIT_DIR}/podman-${_MACHINE}.service" <<UNIT_EOF
[Unit]
Description=Ghost Academy dedicated Podman API (${_MACHINE})
After=network.target

[Service]
Type=simple
Environment=CONTAINERS_CONF=${_GA_CONTAINERS_CONF}
RuntimeDirectory=${_MACHINE}
ExecStart=/usr/bin/podman \\
  --root=${_STORAGE_ROOT} \\
  --runroot=${_RUNTIME_DIR}/${_MACHINE}-containers \\
  system service --time=0 unix://${_RUNTIME_DIR}/${_MACHINE}/podman.sock
Restart=on-failure

[Install]
WantedBy=default.target
UNIT_EOF

    echo "✓ Systemd service unit written to ${_UNIT_DIR}"

    # Remove any stale socket-activation unit from a previous install
    rm -f "${_UNIT_DIR}/podman-${_MACHINE}.socket" 2>/dev/null || true

    # Reload and start the service directly (no socket activation)
    systemctl --user daemon-reload
    systemctl --user enable --now "podman-${_MACHINE}.service"

    # Enable lingering for reboot survival
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
    echo "✓ Linger enabled — dedicated instance survives logout/reboot"

    # Set socket path — service creates it under its own RuntimeDirectory
    PODMAN_SOCK="${_RUNTIME_DIR}/${_MACHINE}/podman.sock"

    # Validate the socket file exists. The service creates it on startup so
    # a file-existence check is reliable (unlike socket activation).
    _sock_tries=0
    while [[ ! -S "$PODMAN_SOCK" ]] && (( _sock_tries < 10 )); do
      sleep 1
      (( _sock_tries++ )) || true
    done
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      echo "⚠ Dedicated Podman socket not reachable at: ${PODMAN_SOCK}" >&2
      echo "  Check: systemctl --user status podman-${_MACHINE}.service" >&2
      echo "  Journal: journalctl --user -u podman-${_MACHINE}.service" >&2
      exit 1
    fi
    echo "✓ Dedicated podman socket: ${PODMAN_SOCK}"
  else
    # ── Default Podman instance (Linux, existing behaviour) ──────────────────
    # `podman.socket` gives us the rootless API socket on demand; `enable --now`
    # so it's live immediately, not just on next login.
    systemctl --user enable --now podman.socket 2>/dev/null || true
    systemctl --user enable podman-restart.service 2>/dev/null || true
    echo "✓ podman.socket + podman-restart.service enabled"

    # Enable lingering so systemd user units (and thus the transport container)
    # survive logout. Without this, headless servers tear down the user slice
    # when the last session ends, silently killing the transport.
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
    echo "✓ Linger enabled — transport survives logout/reboot"

    # Socket path: honour an existing PODMAN_SOCK env var (user override) or
    # default to the standard rootless path.
    if [[ -z "${PODMAN_SOCK:-}" ]]; then
      PODMAN_SOCK="/run/user/$(id -u)/podman/podman.sock"
    fi

    # Validate that the socket actually exists (podman.socket activation may
    # need a moment). Bounded retry: up to 5 seconds.
    _sock_tries=0
    while [[ ! -S "$PODMAN_SOCK" ]] && (( _sock_tries < 5 )); do
      sleep 1
      (( _sock_tries++ )) || true
    done
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      echo "⚠ Podman socket not found at: ${PODMAN_SOCK}" >&2
      echo "  Expected path: /run/user/$(id -u)/podman/podman.sock" >&2
      echo "  Check: podman info --format '{{.Host.RemoteSocket.Path}}'" >&2
      echo "  Override: set PODMAN_SOCK=/your/path before running install.sh" >&2
      exit 1
    fi
    echo "✓ podman socket: ${PODMAN_SOCK}"
  fi

  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${GA_MACHINE_NAME}/data"

  # SELinux & container labels:
  # `--security-opt label=disable` (applied to the transport container below)
  # disables SELinux label confinement for bind-mounted paths. This is necessary
  # because the podman socket is labeled user_tmp_t, which the container's
  # confined domain cannot access — producing a silent "Permission denied".
  #
  # Trade-off: on SELinux-enforcing hosts (Fedora/RHEL/CentOS), this means the
  # transport container runs without MAC-layer confinement. The blast radius is
  # limited: the container is rootless and binds only to localhost. For hardened
  # environments that require full SELinux enforcement, see
  # docs/troubleshooting.md for guidance on supplying a custom policy.
  #
  # On non-SELinux hosts (Debian/Ubuntu), this flag is a no-op.
fi

mkdir -p "$DATA_DIR"

# ga-kiro-auth persists as a plain file under DATA_DIR (ga-kiro-auth),
# written directly by transport itself once a login completes — install.sh
# doesn't need to touch it at all, since the existing -v "${DATA_DIR}:/data"
# mount below already gives transport read/write access to it.
echo "✓ transport data dir ready: ${DATA_DIR}"

# GA_API_KEY persistence: a plain file in DATA_DIR, the same pattern
# ga-kiro-auth already uses — not a Podman secret, since server.py just
# wants a plain env var and DATA_DIR already survives reinstalls.
# --api-key <key> sets/overwrites it; --api-key "" (empty) explicitly
# clears it; omitting the flag entirely reuses whatever was last persisted.
API_KEY_PROJECTION="${DATA_DIR}/ga-api-key"
if [[ "$API_KEY_FLAG_PASSED" == "1" ]]; then
  if [[ -n "${GA_API_KEY:-}" ]]; then
    (umask 077; printf '%s' "$GA_API_KEY" > "$API_KEY_PROJECTION")
    chmod 600 "$API_KEY_PROJECTION"
    echo "✓ API key saved to ${API_KEY_PROJECTION} (reused automatically on future installs)"
  else
    rm -f "$API_KEY_PROJECTION"
    echo "✓ API key cleared — pass --api-key <key> again to re-enable"
  fi
elif [[ -s "$API_KEY_PROJECTION" ]]; then
  GA_API_KEY="$(cat "$API_KEY_PROJECTION")"
  echo "✓ API key restored from ${API_KEY_PROJECTION}"
fi

# ── Resolve dedicated-instance podman command ────────────────────────────────

# On Linux with a dedicated instance, all podman commands (network, pull,
# build, secret, run) must target the dedicated storage root so every
# resource lands on the same instance. On macOS with a dedicated machine,
# use --connection to target it. For the default instance, bare `podman`
# just works. Resolved once and reused below so no step is accidentally
# left targeting the wrong instance.
if [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Linux" ]]; then
  _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  _STORAGE_ROOT="${HOME}/.local/share/${GA_MACHINE_NAME}/containers/storage"
  _GA_CONTAINERS_CONF="${HOME}/.config/${GA_MACHINE_NAME}/containers.conf"

  # ── WSL2: write a ghostship-scoped containers.conf ────────────────────────
  # Written unconditionally to a ghostship-owned path so it never affects the
  # user's default Podman. On non-WSL2 hosts the file is empty (comment-only),
  # a no-op. The dedicated service unit sets CONTAINERS_CONF to this file.
  mkdir -p "$(dirname "${_GA_CONTAINERS_CONF}")"
  if grep -qi "microsoft" /proc/version 2>/dev/null; then
    # WSL2 doesn't support nftables — ensure iptables is available before
    # writing the config that tells Podman to use it.
    if ! command -v iptables >/dev/null 2>&1; then
      echo "WSL2 detected — installing iptables..."
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y -qq iptables
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y -q iptables
      else
        echo "⚠ Could not install iptables automatically — install it manually before continuing" >&2
      fi
    fi
    cat > "${_GA_CONTAINERS_CONF}" <<CONF_EOF
# ghostship-scoped containers.conf — generated by install.sh
# Scoped to the dedicated '${GA_MACHINE_NAME}' Podman instance only.
# WSL2: use iptables instead of nftables for bridge networking.
[network]
firewall_driver = "iptables"
CONF_EOF
    echo "✓ WSL2 detected — scoped iptables workaround written to ${_GA_CONTAINERS_CONF}"
  else
    cat > "${_GA_CONTAINERS_CONF}" <<CONF_EOF
# ghostship-scoped containers.conf — generated by install.sh
# Scoped to the dedicated '${GA_MACHINE_NAME}' Podman instance only.
CONF_EOF
  fi

  # Prefix CONTAINERS_CONF so all podman subcommands (network, build, run, …)
  # pick up the ghostship-scoped config (WSL2 iptables workaround etc.) without
  # touching the user's default Podman configuration.
  _PODMAN_CMD="env CONTAINERS_CONF=${_GA_CONTAINERS_CONF} podman --root=${_STORAGE_ROOT} --runroot=${_RUNTIME_DIR}/${GA_MACHINE_NAME}-containers"
elif [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Darwin" ]]; then
  _PODMAN_CMD="podman --connection ${GA_MACHINE_NAME}"
else
  _PODMAN_CMD="podman"
fi

# ── Network ───────────────────────────────────────────────────────────────────

${_PODMAN_CMD} network exists ga-portside 2>/dev/null || ${_PODMAN_CMD} network create ga-portside
${_PODMAN_CMD} network exists ga-starboard 2>/dev/null || ${_PODMAN_CMD} network create ga-starboard
if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
  echo "✓ ga-portside and ga-starboard networks ready on dedicated instance '${GA_MACHINE_NAME}' (DNS-enabled by default)"
else
  echo "✓ ga-portside and ga-starboard networks ready (DNS-enabled by default)"
fi

# ── Pre-warm + build images ──────────────────────────────────────────────────


VERSION="$(cat "$GHOSTSHIP_DIR/VERSION")"

# Some build backends (observed with podman) do not reliably invalidate a
# cached layer when only a --build-arg value changes, silently baking a
# stale VERSION into an image whose tag/creation time otherwise look fresh.
# Detect that here and force --no-cache ONLY when the currently-tagged
# image's baked version actually differs from VERSION -- an ordinary
# reinstall with no version bump still gets the normal cache speed-up.
_TRANSPORT_BUILD_FLAGS=()
if ${_PODMAN_CMD} image exists localhost/transport:latest 2>/dev/null; then
  _baked_transport_version="$(${_PODMAN_CMD} run --rm localhost/transport:latest sh -c 'echo $TRANSPORT_VERSION' 2>/dev/null || true)"
  if [[ "$_baked_transport_version" != "$VERSION" ]]; then
    echo "  Detected stale localhost/transport:latest version ('$_baked_transport_version' != '$VERSION') -- forcing a clean rebuild."
    _TRANSPORT_BUILD_FLAGS=(--no-cache)
  fi
fi

_CREW_BUILD_FLAGS=()
if ${_PODMAN_CMD} image exists localhost/spec-ops:latest 2>/dev/null; then
  _baked_crew_version="$(${_PODMAN_CMD} inspect localhost/spec-ops:latest --format '{{ index .Labels "org.ghostship.version" }}' 2>/dev/null || true)"
  if [[ "$_baked_crew_version" != "${VERSION}-spec-ops" ]]; then
    echo "  Detected stale localhost/spec-ops:latest version ('$_baked_crew_version' != '${VERSION}-spec-ops') -- forcing a clean rebuild."
    _CREW_BUILD_FLAGS=(--no-cache)
  fi
fi

echo "Building localhost/base-admission:latest (admission) ..."
# Copy container-side helper scripts into the admission build context so they
# are baked into the crew image at /scripts/ (TRN-74). Uses a temp copy to
# avoid polluting the source tree with generated files.
_ADMISSION_CTX="$(mktemp -d)"
cp -r "$GHOSTSHIP_DIR/crews/_base/admission/." "$_ADMISSION_CTX/"
mkdir -p "$_ADMISSION_CTX/container_scripts"
cp "$GHOSTSHIP_DIR/transport/container_scripts/"*.py "$_ADMISSION_CTX/container_scripts/"
${_PODMAN_CMD} build -t localhost/base-admission:latest \
  "$_ADMISSION_CTX/" \
  && echo "✓ admission image built" || { echo "✗ admission image build failed"; rm -rf "$_ADMISSION_CTX"; exit 1; }
rm -rf "$_ADMISSION_CTX"

# Worker image (TRN-81) — the transport's disposable utility unit for reading
# files/bundles/diffs from STOPPED crew volumes without waking the crew. Based
# on python:3.12.10-slim (shared with the transport image) plus git. Built
# after base-admission and before the crew compositions.
echo "Building localhost/gs-worker:latest (worker) ..."
${_PODMAN_CMD} build -t localhost/gs-worker:latest \
  --build-arg VERSION="${VERSION}" \
  "$GHOSTSHIP_DIR/crews/_worker/" \
  && echo "✓ worker image built" || { echo "✗ worker image build failed"; exit 1; }

echo "Building localhost/spec-ops:latest ..."
${_PODMAN_CMD} build -t localhost/spec-ops-mid:latest \
  "${_CREW_BUILD_FLAGS[@]}" \
  --build-arg VERSION="${VERSION}-spec-ops" \
  "$GHOSTSHIP_DIR/crews/spec-ops/" \
  && ${_PODMAN_CMD} build -t localhost/spec-ops:latest \
  "${_CREW_BUILD_FLAGS[@]}" \
  --build-arg MID_IMAGE=localhost/spec-ops-mid:latest \
  "$GHOSTSHIP_DIR/crews/_base/graduation/" \
  && echo "✓ crew image built" || { echo "✗ crew image build failed"; exit 1; }

echo "Building localhost/transport:latest ..."
${_PODMAN_CMD} build -t localhost/transport:latest \
  "${_TRANSPORT_BUILD_FLAGS[@]}" \
  --build-arg VERSION="${VERSION}" \
  "$GHOSTSHIP_DIR/transport/" \
  && echo "✓ transport image built" || { echo "✗ transport image build failed"; exit 1; }

# ── Podman secret for GA_API_KEY ──────────────────────────────────────────────

${_PODMAN_CMD} secret rm ga-api-key 2>/dev/null || true
GA_SECRET_FLAG=""
if [[ -n "${GA_API_KEY:-}" ]]; then
  printf '%s' "$GA_API_KEY" | ${_PODMAN_CMD} secret create ga-api-key -
  GA_SECRET_FLAG="secrets:\n      - ga-api-key"
  echo "✓ Podman secret 'ga-api-key' created"
fi

# ── Podman secret for GA_TRANSPORT_SECRET (TRN-107) ─────────────────────────────
# Idempotent: only generate if the secret does not already exist. This ensures
# the same secret is reused across reinstalls (Caddy and transport stay in sync).
if ! ${_PODMAN_CMD} secret inspect ga-transport-secret >/dev/null 2>&1; then
  openssl rand -hex 32 | ${_PODMAN_CMD} secret create ga-transport-secret -
  echo "✓ Podman secret 'ga-transport-secret' created (new)"
else
  echo "✓ Podman secret 'ga-transport-secret' already exists (keeping existing)"
fi

# ── Copy academy/ and crews/ into the data volume ────────────────────────────
# Snapshot academy/ subdirectories and crews/ from the repo into DATA_DIR so
# the transport container has no runtime dependency on the repo checkout path.
# Changes to these directories require re-running install.sh to take effect.
mkdir -p "${DATA_DIR}/academy"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/agents"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/skills"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/steering"  "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/policies"  "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/orders"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/mcp"       "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/crews"             "${DATA_DIR}/"
else
  echo "  rsync not found — falling back to cp (deletions from repo not mirrored until full reinstall)"
  rm -rf "${DATA_DIR}/academy/agents" "${DATA_DIR}/academy/skills" \
         "${DATA_DIR}/academy/steering" "${DATA_DIR}/academy/policies" \
         "${DATA_DIR}/academy/orders" "${DATA_DIR}/academy/mcp" "${DATA_DIR}/crews"
  cp -r "${GHOSTSHIP_DIR}/academy/agents"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/skills"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/steering"  "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/policies"  "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/orders"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/mcp"       "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/crews"             "${DATA_DIR}/"
fi
echo "✓ academy/ (agents, skills, steering, policies, orders, mcp) and crews/ copied to ${DATA_DIR}"

# ── Generate compose.yml ──────────────────────────────────────────────────────
# Written to DATA_DIR so it is machine-specific (socket path, env vars) and
# not committed to the repo. start.sh and uninstall.sh both read it.

# Pre-compute UI port range end for the compose template.
_DASHBOARD_PORT_START="${GA_DASHBOARD_PORT_RANGE_START:-64058}"
_DASHBOARD_PORT_END=$(( _DASHBOARD_PORT_START + ${GA_DASHBOARD_PORT_RANGE_SIZE:-50} - 1 ))

cat > "${DATA_DIR}/compose.yml" <<COMPOSE_EOF
# Generated by install.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ') — do not edit manually.
# Re-run install.sh to regenerate.
services:
  ga-transport:
    image: localhost/transport:latest
    container_name: ga-transport
    restart: always
    security_opt:
      - label=disable
    networks:
      - ga-portside
      - ga-starboard
    volumes:
      - ${DATA_DIR}:/data
      - ${DATA_DIR}/academy/agents:/agents:ro
      - ${DATA_DIR}/academy/skills:/skills:ro
      - ${DATA_DIR}/academy/steering:/steering:ro
      - ${DATA_DIR}/academy/policies:/policies:ro
      - ${DATA_DIR}/academy/orders:/orders:ro
      - ${DATA_DIR}/academy/mcp:/mcp:ro
      - ${DATA_DIR}/crews:/crews:ro
      - ${PODMAN_SOCK}:${PODMAN_SOCK}
    environment:
      PODMAN_SOCKET: ${PODMAN_SOCK}
      HOST: ${HOST:-0.0.0.0}
      PORT: "${PORT}"
      GA_HOST_URL: "${GA_HOST_URL:-http://localhost:${PORT}}"
      GA_MAX_CREWS: "${GA_MAX_CREWS:-20}"
      GA_MAX_ACTIVE_CREWS: "${GA_MAX_ACTIVE_CREWS:-3}"
      GA_IDLE_TIMEOUT_SECS: "${GA_IDLE_TIMEOUT_SECS:-300}"
      GA_SUBAGENT_TIMEOUT_SECS: "${GA_SUBAGENT_TIMEOUT_SECS:-3600}"
      GA_SUBAGENT_MAX_TURNS: "${GA_SUBAGENT_MAX_TURNS:-200}"
      GA_CREW_AGENT: "${GA_CREW_AGENT:-kiro}"
      KIRO_IDENTITY_PROVIDER: "${KIRO_IDENTITY_PROVIDER:-}"
      KIRO_REGION: "${KIRO_REGION:-}"
      KIRO_LICENSE: "${KIRO_LICENSE:-}"
      KIRO_API_KEY: "${KIRO_API_KEY:-}"
      KC_MODEL_OVERRIDE: "${KC_MODEL_OVERRIDE:-}"
      KC_MODEL_DEFAULT: "${KC_MODEL_DEFAULT:-}"
      GA_MIN_FREE_MEM_GB: "${GA_MIN_FREE_MEM_GB:-2.0}"
      GA_SPAWN_MIN_MEMORY_GB: "${GA_SPAWN_MIN_MEMORY_GB:-1.5}"
      GA_RESOURCE_PRESSURE_GB: "${GA_RESOURCE_PRESSURE_GB:-2.0}"
      GA_RESOURCE_CRITICAL_GB: "${GA_RESOURCE_CRITICAL_GB:-1.0}"
      GA_GIT_AUTHOR_NAME: "${GA_GIT_AUTHOR_NAME:-}"
      GA_GIT_AUTHOR_EMAIL: "${GA_GIT_AUTHOR_EMAIL:-}"
      GA_ENABLE_SECURITY_HEADERS: "${GA_ENABLE_SECURITY_HEADERS:-1}"
      GA_TLS_MIN_VERSION: "${GA_TLS_MIN_VERSION:-1.2}"
      GA_TLS_CERTFILE: "${GA_TLS_CERTFILE:-}"
      GA_TLS_KEYFILE: "${GA_TLS_KEYFILE:-}"
      GA_RATE_LIMIT_ENABLED: "${GA_RATE_LIMIT_ENABLED:-true}"
      GA_RATE_LIMIT_LOGIN_GET: "${GA_RATE_LIMIT_LOGIN_GET:-30:60}"
      GA_RATE_LIMIT_LOGIN_POST: "${GA_RATE_LIMIT_LOGIN_POST:-5:300}"
      GA_RATE_LIMIT_MCP: "${GA_RATE_LIMIT_MCP:-300:60}"
      GA_RATE_LIMIT_FILES: "${GA_RATE_LIMIT_FILES:-60:60}"
      GA_RATE_LIMIT_CREW_API: "${GA_RATE_LIMIT_CREW_API:-120:60}"
      GA_DASHBOARD_PORT_RANGE_START: "${GA_DASHBOARD_PORT_RANGE_START:-64058}"
      GA_DASHBOARD_PORT_RANGE_SIZE: "${GA_DASHBOARD_PORT_RANGE_SIZE:-50}"
      GA_DASHBOARD_PORT_ENABLED: "${GA_DASHBOARD_PORT_ENABLED:-true}"
      GA_PORTAL_TLS_MODE: "${GA_PORTAL_TLS_MODE:-off}"
      GA_PORTAL_DOMAIN: "${GA_PORTAL_DOMAIN:-}"
    secrets:
      - ga-transport-secret
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '      - ga-api-key\n'; fi)
  ga-portal:
    image: docker.io/caddy:2
    container_name: ga-portal
    restart: always
    ports:
      - "0.0.0.0:${PORT:-64057}:${PORT:-64057}"
      - "${_DASHBOARD_PORT_START}-${_DASHBOARD_PORT_END}:${_DASHBOARD_PORT_START}-${_DASHBOARD_PORT_END}"
    networks:
      - ga-portside
    environment:
      GA_API_KEY: "${GA_API_KEY:-}"
    secrets:
      - ga-transport-secret
    volumes:
      - ${DATA_DIR}/caddy/initial-config.json:/config/initial-config.json:ro
      - ga-portal-data:/data
    command: ["caddy", "run", "--config", "/config/initial-config.json", "--resume"]
networks:
  ga-portside:
    external: true
  ga-starboard:
    external: true
secrets:
  ga-transport-secret:
    external: true
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '  ga-api-key:\n    external: true\n'; fi)
volumes:
  ga-portal-data:
COMPOSE_EOF

echo "✓ compose.yml written to ${DATA_DIR}/compose.yml"

# ── Generate Caddy initial-config.json (TRN-92 / TRN-103) ─────────────────────
# ga-portal (Caddy) is always installed. This config bootstraps the main-port
# server with Bearer-gated MCP/file routes and the dashboard-auth endpoints.
# Per-crew dashboard servers are added at runtime via the Caddy admin API.
mkdir -p "${DATA_DIR}/caddy"

# Build the TLS stanza based on GA_PORTAL_TLS_MODE.
_AUTO_HTTPS=""  # set to disable auto-HTTPS for TLS_MODE=off
case "${GA_PORTAL_TLS_MODE:-off}" in
  tailscale)
    _TLS_STANZA='"tls": {"automation": {"policies": [{"get_certificate": [{"via": "tailscale"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
  acme)
    _ACME_DOMAIN="${GA_PORTAL_DOMAIN:-}"
    _TLS_STANZA='"tls": {"automation": {"policies": [{"subjects": ["'"${_ACME_DOMAIN}"'"], "issuers": [{"module": "acme"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
  off)
    # Plain HTTP — disable auto-HTTPS, listen on the HTTP port.
    _TLS_STANZA='"tls": {}'
    _MAIN_LISTEN=":${PORT:-64057}"
    _AUTO_HTTPS='"automatic_https": {"disable": true},'
    ;;
  *)  # internal (default)
    _TLS_STANZA='"tls": {"automation": {"policies": [{"issuers": [{"module": "internal"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
esac

# The portal-token header injected on every upstream request (TRN-107).
# Caddy reads the secret from the mounted Podman secret file using the
# {file.<path>} placeholder (Caddy v2.7+).
_PORTAL_TOKEN_HEADER='"headers": {"request": {"set": {"X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]}}}'

# Build auth routes: gated when GA_API_KEY is set, open passthrough otherwise.
if [[ -n "${GA_API_KEY:-}" ]]; then
  _AUTH_ROUTES=$(cat <<AUTH_EOF
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"], "header": {"Authorization": ["Bearer {env.GA_API_KEY}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:${PORT}"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"], "header": {"Authorization": ["Bearer {env.GA_API_KEY}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:${PORT}"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-mcp-files-reject",
              "match": [{"path": ["/mcp*", "/files/*"]}],
              "handle": [{"handler": "static_response", "status_code": 401, "headers": {"Www-Authenticate": ["Bearer"]}, "body": "Unauthorized"}]
            },
AUTH_EOF
)
else
  # No API key — pass all routes through to the transport (Tailscale-gated).
  _AUTH_ROUTES=$(cat <<AUTH_EOF
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:${PORT}"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:${PORT}"}], ${_PORTAL_TOKEN_HEADER}}]
            },
AUTH_EOF
)
fi

# Generate initial-config.json — main server only, no per-crew servers.
cat > "${DATA_DIR}/caddy/initial-config.json" <<CADDY_EOF
{
  "admin": {"listen": "0.0.0.0:2019"},
  "apps": {
    "http": {
      "servers": {
        "ga-main": {
          "listen": ["${_MAIN_LISTEN}"],
          ${_AUTO_HTTPS}
          "routes": [
${_AUTH_ROUTES}
            {
              "@id": "ga-transport-misc",
              "match": [{"path": ["/health", "/version", "/dashboard-auth", "/dashboard-auth*", "/login-ui", "/dashboard-login", "/login", "/login*", "/logout"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:${PORT}"}], ${_PORTAL_TOKEN_HEADER}}]
            }
          ]
        }
      }
    },
    ${_TLS_STANZA}
  }
}
CADDY_EOF

echo "✓ Caddy initial-config.json written to ${DATA_DIR}/caddy/initial-config.json"

# Internal CA: surface the root cert path so the operator knows where to
# run 'caddy trust'. The cert lives in the ga-portal-data volume at the
# standard Caddy path /data/caddy/pki/authorities/local/root.crt.
if [[ "${GA_PORTAL_TLS_MODE:-off}" == "internal" ]]; then
  # Resolve the host-side volume mountpoint for ga-portal-data.
  _CADDY_DATA_MOUNTPOINT=""
  if ${_PODMAN_CMD} volume exists ga-portal-data 2>/dev/null; then
    _CADDY_DATA_MOUNTPOINT="$(${_PODMAN_CMD} volume inspect ga-portal-data --format '{{.Mountpoint}}' 2>/dev/null || true)"
  fi
  _CADDY_ROOT_CERT_PATH="${_CADDY_DATA_MOUNTPOINT:-(ga-portal-data not yet created)}/caddy/pki/authorities/local/root.crt"
  echo ""
  echo "── Caddy internal CA ─────────────────────────────────────────────────"
  echo "TLS mode: internal (Caddy built-in CA)"
  echo "Root CA cert: ${_CADDY_ROOT_CERT_PATH}"
  echo ""
  echo "After ga-portal starts, run this once to trust the CA:"
  echo "  podman exec ga-portal caddy trust"
  echo "or import the cert manually from the path above."
  echo "──────────────────────────────────────────────────────────────────────"
  echo ""
fi

# ── Run transport ─────────────────────────────────────────────────────────────

# Kill any stale rootlessport process that may be holding the transport port
# open from a previous (possibly interrupted) install. These survive container
# removal and will cause compose up to fail with "address already in use".
# ga-transport no longer binds a host port (Caddy is the external listener),
# so only check for stale rootlessport on ga-portal's port (PORT).
for _pid in $(pgrep -x rootlessport 2>/dev/null); do
  if ss -tlnp 2>/dev/null | grep -q "0.0.0.0:${PORT:-64057}.*pid=${_pid}"; then
    kill "$_pid" 2>/dev/null && echo "✓ killed stale rootlessport on port ${PORT:-64057} (pid ${_pid})" || true
    sleep 0.5
  fi
done

# The external podman-compose provider is shelled out to as a separate
# process, so CLI flags like --connection or --root/--runroot on the outer
# `podman compose` invocation are NOT inherited by its internal podman calls
# — only environment variables are. Point it at the right instance via
# CONTAINER_HOST for the dedicated Linux instance, or CONTAINER_CONNECTION
# for the dedicated macOS machine (bare `podman` would otherwise resolve via
# whatever the ambient default connection happens to be, which may not be
# '${GA_MACHINE_NAME}'). Non-dedicated installs use the default either way.
if [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Linux" ]]; then
  _COMPOSE_ENV="CONTAINER_HOST=unix://${PODMAN_SOCK}"
elif [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Darwin" ]]; then
  _COMPOSE_ENV="CONTAINER_CONNECTION=${GA_MACHINE_NAME}"
else
  _COMPOSE_ENV=""
fi
eval "${_COMPOSE_ENV} podman rm -f ga-transport" >/dev/null 2>&1 || true
eval "${_COMPOSE_ENV} podman rm -f ga-portal" >/dev/null 2>&1 || true
eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${DATA_DIR}/compose.yml\" up -d --force-recreate --remove-orphans"
echo "✓ ga-transport container started"

if [[ -n "${GA_API_KEY:-}" ]]; then
  echo "✓ MCP API-key authentication: enabled (see docs/auth.md for client header setup)"
else
  echo "  MCP API-key authentication: disabled (pass --api-key <key> to enable)"
fi

sleep 1  # brief pause before first probe attempt
echo ""
echo "=== Health check ==="
_max_wait=30
_interval=2
_ready=0
# Transport has no host port (Caddy is the external listener). Probe via
# podman exec so we don't need a host-side binding.
for (( _i=0; _i<_max_wait; _i+=_interval )); do
  if ${_PODMAN_CMD} exec ga-transport python3 -c "
import urllib.request, os
secret = open('/run/secrets/ga-transport-secret').read().strip() if os.path.exists('/run/secrets/ga-transport-secret') else ''
req = urllib.request.Request('http://127.0.0.1:${PORT}/health', headers={'X-Transport-Token': secret})
urllib.request.urlopen(req)
" >/dev/null 2>&1; then
    _ready=1
    break
  fi
  sleep "$_interval"
done
if [[ "$_ready" == "1" ]]; then
  echo "✓ Transport is ready (container-internal health check passed)"
else
  echo "✗ Transport did not become ready within ${_max_wait}s" >&2
  echo "  Last 20 lines of container logs:" >&2
  ${_PODMAN_CMD} logs ga-transport --tail 20 >&2
  exit 1
fi

# TRN-103: ga-portal health check (Caddy is always installed)
_caddy_ready=0
_caddy_scheme="http"
[[ "${GA_PORTAL_TLS_MODE:-off}" != "off" ]] && _caddy_scheme="https"
for (( _i=0; _i<_max_wait; _i+=_interval )); do
  if curl -sk "${_caddy_scheme}://127.0.0.1:${PORT:-64057}/health" >/dev/null 2>&1; then
    _caddy_ready=1
    break
  fi
  sleep "$_interval"
done
if [[ "$_caddy_ready" == "1" ]]; then
  echo "✓ Caddy is ready"
else
  echo "⚠ Caddy (ga-portal) did not respond on port ${PORT:-64057} within ${_max_wait}s"
  echo "  Check: ${_PODMAN_CMD} logs ga-portal --tail 20"
  echo "  This is non-fatal — Caddy may still be pulling or starting."
fi

echo ""
echo "=== Post-install ==="

# ── Best-effort ga-net cleanup (TRN-107) ─────────────────────────────────────
# If ga-net exists and has no containers, remove it (migration complete).
# This is a no-op on fresh installs. Silently skipped if the network still
# has containers (migration will run at transport startup via _reconcile_registry).
if ${_PODMAN_CMD} network exists ga-net 2>/dev/null; then
  _ga_net_containers="$(${_PODMAN_CMD} network inspect ga-net --format '{{len .Containers}}' 2>/dev/null || echo "1")"
  if [[ "${_ga_net_containers}" == "0" ]]; then
    ${_PODMAN_CMD} network rm ga-net >/dev/null 2>&1 \
      && echo "✓ ga-net removed (empty, migration complete)" \
      || echo "  ga-net removal skipped (in use or error)"
  else
    echo "  ga-net still has ${_ga_net_containers} container(s) — will be migrated at transport startup"
  fi
fi
echo "Register the MCP server (one-time):"
echo "  kiro-cli mcp add --name ghostship --url http://localhost:${PORT}/mcp --scope global"
echo ""
echo "Then from Kiro CLI, create the first crew:"
echo "  ghostship__launch(crew_id=\"general\")"
echo ""
echo "On first launch you'll be prompted to authenticate kiro-cli inside the"
echo "crew container. Open the returned URL, then call launch again with the"
echo "same crew_id to finish setup."

# ── Make ghostship available on PATH ─────────────────────────────────────────
_LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "${_LOCAL_BIN}"
ln -sf "${GHOSTSHIP_DIR}/ghostship" "${_LOCAL_BIN}/ghostship"
echo ""
echo "✓ ghostship CLI linked to ${_LOCAL_BIN}/ghostship"
if [[ ":${PATH}:" != *":${_LOCAL_BIN}:"* ]]; then
  echo "  Add ~/.local/bin to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
