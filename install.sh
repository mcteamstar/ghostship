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

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

# ── Built-in defaults (literal assignments, BEFORE config sourcing) ──────────
# Resolution order: built-in default → config file → CLI flag.
# A literal assignment here ensures an ambient env var from the invoking shell
# is unconditionally overwritten — only the config file or a flag can override.
PORT=64057
GA_FILE_PUBLIC_URL=""
GA_MCP_PUBLIC_URL=""
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
GA_FILE_TTL_SECS=300
GA_SUBAGENT_TIMEOUT_SECS=3600
GA_SUBAGENT_MAX_TURNS=200
GA_PICKUP_MAX_POLL_SECS=30
KC_GATEWAY_TOKEN_TTL=24h
GA_MIN_FREE_MEM_GB=2.0
GA_MEMORY_WAIT_SECS=60
GA_SPAWN_MIN_MEMORY_GB=1.5
GA_RESOURCE_PRESSURE_GB=2.0
GA_RESOURCE_CRITICAL_GB=1.0
HOST=0.0.0.0

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
  # TRUST ASSUMPTION: this executes arbitrary shell code from the path the user
  # passed via --config. The caller is trusted — this is intentional: config
  # files export env vars that control identity provider, region, API keys, etc.
  # Do NOT source untrusted paths.
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
  echo "✓ Sourced config file: $CONFIG_FILE"
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
    --file-public-url) GA_FILE_PUBLIC_URL="$2"; shift 2 ;;
    --mcp-public-url) GA_MCP_PUBLIC_URL="$2"; shift 2 ;;
    --public-url) GA_HOST_URL="$2"; shift 2 ;;
    --api-key) GA_API_KEY="$2"; API_KEY_FLAG_PASSED=1; shift 2 ;;
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
  case "$OS" in
    Darwin)
      command -v brew >/dev/null 2>&1 || {
        echo "Homebrew not found — install it from https://brew.sh, or install podman yourself." >&2
        exit 1
      }
      echo "Installing podman via Homebrew..."
      brew install podman
      ;;
    Linux)
      if command -v apt-get >/dev/null 2>&1; then
        echo "Installing podman via apt..."
        sudo apt-get update -qq && sudo apt-get install -y -qq podman
      elif command -v dnf >/dev/null 2>&1; then
        echo "Installing podman via dnf..."
        sudo dnf install -y -q podman
      else
        echo "No supported package manager found (looked for apt-get, dnf)." >&2
        echo "" >&2
        echo "Minimum requirements to continue:" >&2
        echo "  • podman >= 4.0" >&2
        echo "  • crun or runc (OCI runtime)" >&2
        echo "  • slirp4netns or pasta (rootless networking)" >&2
        echo "" >&2
        echo "See docs/manual-install.md for example commands (Arch, Alpine, Nix)." >&2
        echo "" >&2
        if [[ -t 0 ]]; then
          echo "Install podman manually, then press Enter to continue (or Ctrl-C to abort)." >&2
          read -r
        fi
        if ! command -v podman >/dev/null 2>&1; then
          echo "podman still not found on PATH — cannot continue." >&2
          exit 1
        fi
        echo "✓ podman found after manual install"
      fi
      ;;
    *)
      echo "Unsupported OS: $OS (this script supports macOS and Linux)" >&2
      exit 1
      ;;
  esac
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

${_PODMAN_CMD} network exists ga-net 2>/dev/null || ${_PODMAN_CMD} network create ga-net
if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
  echo "✓ ga-net network ready on dedicated instance '${GA_MACHINE_NAME}' (DNS-enabled by default)"
else
  echo "✓ ga-net network ready (DNS-enabled by default)"
fi

# ── Pre-warm + build images ──────────────────────────────────────────────────

${_PODMAN_CMD} pull ghcr.io/kirodotdev/kirocrew:stable -q 2>/dev/null \
  && echo "✓ KiroCrew image pre-warmed" || echo "⚠ KiroCrew image pull failed (offline?)"

VERSION="$(cat "$GHOSTSHIP_DIR/VERSION")"

echo "Building localhost/base-orientation:latest (orientation) ..."
${_PODMAN_CMD} build -t localhost/base-orientation:latest \
  "$GHOSTSHIP_DIR/crews/_base/orientation/" \
  && echo "✓ orientation image built" || { echo "✗ orientation image build failed"; exit 1; }

echo "Building localhost/spec-ops:latest ..."
${_PODMAN_CMD} build -t localhost/spec-ops-mid:latest \
  --build-arg VERSION="${VERSION}-spec-ops" \
  "$GHOSTSHIP_DIR/crews/spec-ops/" \
  && ${_PODMAN_CMD} build -t localhost/spec-ops:latest \
  --build-arg MID_IMAGE=localhost/spec-ops-mid:latest \
  "$GHOSTSHIP_DIR/crews/_base/graduation/" \
  && echo "✓ crew image built" || { echo "✗ crew image build failed"; exit 1; }

echo "Building localhost/transport:latest ..."
${_PODMAN_CMD} build -t localhost/transport:latest "$GHOSTSHIP_DIR/transport/" \
  && echo "✓ transport image built" || { echo "✗ transport image build failed"; exit 1; }

# ── Podman secret for GA_API_KEY ──────────────────────────────────────────────

${_PODMAN_CMD} secret rm ga-api-key 2>/dev/null || true
GA_SECRET_FLAG=""
if [[ -n "${GA_API_KEY:-}" ]]; then
  printf '%s' "$GA_API_KEY" | ${_PODMAN_CMD} secret create ga-api-key -
  GA_SECRET_FLAG="--secret ga-api-key"
  echo "✓ Podman secret 'ga-api-key' created"
fi

# ── Run transport ─────────────────────────────────────────────────────────────

${_PODMAN_CMD} rm -f ga-transport >/dev/null 2>&1 || true

# Kill any stale rootlessport process that may be holding the transport port
# open from a previous (possibly interrupted) install. These survive container
# removal and will cause `podman run` to fail with "address already in use".
for _pid in $(pgrep -x rootlessport 2>/dev/null); do
  if ss -tlnp 2>/dev/null | grep -q "127.0.0.1:${PORT}.*pid=${_pid}"; then
    kill "$_pid" 2>/dev/null && echo "✓ killed stale rootlessport on port ${PORT} (pid ${_pid})" || true
    sleep 0.5
  fi
done

${_PODMAN_CMD} run -d --name ga-transport --restart=always \
  --security-opt label=disable \
  -p "127.0.0.1:${PORT}:${PORT}" \
  --network ga-net \
  -v "${DATA_DIR}:/data" \
  -v "${GHOSTSHIP_DIR}/academy/agents:/agents:ro" \
  -v "${GHOSTSHIP_DIR}/academy/skills:/skills:ro" \
  -v "${GHOSTSHIP_DIR}/academy/steering:/steering:ro" \
  -v "${GHOSTSHIP_DIR}/academy/policies:/policies:ro" \
  -v "${GHOSTSHIP_DIR}/academy/orders:/orders:ro" \
  -v "${GHOSTSHIP_DIR}/crews:/crews:ro" \
  -v "${PODMAN_SOCK}:${PODMAN_SOCK}" \
  -e "PODMAN_SOCKET=${PODMAN_SOCK}" \
  -e "HOST=${HOST:-0.0.0.0}" \
  -e "PORT=${PORT}" \
  -e "GA_HOST_URL=${GA_HOST_URL:-http://localhost:${PORT}}" \
  -e "GA_FILE_PUBLIC_URL=${GA_FILE_PUBLIC_URL:-}" \
  -e "GA_MCP_PUBLIC_URL=${GA_MCP_PUBLIC_URL:-}" \
  -e "GA_MAX_CREWS=${GA_MAX_CREWS:-20}" \
  -e "GA_MAX_ACTIVE_CREWS=${GA_MAX_ACTIVE_CREWS:-3}" \
  -e "GA_IDLE_TIMEOUT_SECS=${GA_IDLE_TIMEOUT_SECS:-300}" \
  -e "GA_FILE_TTL_SECS=${GA_FILE_TTL_SECS:-300}" \
  -e "GA_SUBAGENT_TIMEOUT_SECS=${GA_SUBAGENT_TIMEOUT_SECS:-3600}" \
  -e "GA_SUBAGENT_MAX_TURNS=${GA_SUBAGENT_MAX_TURNS:-200}" \
  -e "GA_PICKUP_MAX_POLL_SECS=${GA_PICKUP_MAX_POLL_SECS:-30}" \
  -e "KC_GATEWAY_TOKEN_TTL=${KC_GATEWAY_TOKEN_TTL:-24h}" \
  -e "KIRO_IDENTITY_PROVIDER=${KIRO_IDENTITY_PROVIDER:-}" \
  -e "KIRO_REGION=${KIRO_REGION:-}" \
  -e "KIRO_LICENSE=${KIRO_LICENSE:-}" \
  -e "KC_MODEL_OVERRIDE=${KC_MODEL_OVERRIDE:-}" \
  -e "KC_MODEL_DEFAULT=${KC_MODEL_DEFAULT:-}" \
  -e "GA_MIN_FREE_MEM_GB=${GA_MIN_FREE_MEM_GB:-2.0}" \
  -e "GA_MEMORY_WAIT_SECS=${GA_MEMORY_WAIT_SECS:-60}" \
  -e "GA_SPAWN_MIN_MEMORY_GB=${GA_SPAWN_MIN_MEMORY_GB:-1.5}" \
  -e "GA_RESOURCE_PRESSURE_GB=${GA_RESOURCE_PRESSURE_GB:-2.0}" \
  -e "GA_RESOURCE_CRITICAL_GB=${GA_RESOURCE_CRITICAL_GB:-1.0}" \
  ${GA_SECRET_FLAG} \
  localhost/transport:latest

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
for (( _i=0; _i<_max_wait; _i+=_interval )); do
  if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    _ready=1
    break
  fi
  sleep "$_interval"
done
if [[ "$_ready" == "1" ]]; then
  echo "✓ Transport is ready (responded on http://127.0.0.1:${PORT}/health)"
else
  echo "✗ Transport did not become ready within ${_max_wait}s" >&2
  echo "  Last 20 lines of container logs:" >&2
  ${_PODMAN_CMD} logs ga-transport --tail 20 >&2
  exit 1
fi

echo ""
echo "=== Post-install ==="
echo "Register the MCP server (one-time):"
echo "  kiro-cli mcp add --name ghostship --url http://localhost:${PORT}/mcp --scope global"
echo ""
echo "Then from Kiro CLI, create the first crew:"
echo "  ghostship__launch(crew_id=\"general\")"
echo ""
echo "On first launch you'll be prompted to authenticate kiro-cli inside the"
echo "crew container. Open the returned URL, then call launch again with the"
echo "same crew_id to finish setup."
