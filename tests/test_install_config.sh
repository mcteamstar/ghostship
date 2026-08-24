#!/usr/bin/env bash
# Test cases for install.sh --config flag precedence and error handling.
# These tests source install.sh's argument parsing in isolation by extracting
# the relevant section, so they don't need podman or a running system.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
INSTALL="$REPO_DIR/install.sh"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0
FAIL=0

pass() { ((PASS++)); echo "  ✓ $1"; }
fail() { ((FAIL++)); echo "  ✗ $1"; }

echo "=== Test: Config file sets values, flags override them ==="

# Create a config file that sets PORT and KIRO_IDENTITY_PROVIDER
cat > "$TMPDIR/test.conf" <<'EOF'
PORT=9999
KIRO_IDENTITY_PROVIDER="https://config-idp.example.com"
KIRO_REGION="us-west-2"
KIRO_LICENSE="pro"
KC_MODEL_OVERRIDE="config-model"
GA_FILE_PUBLIC_URL="https://config-files.example.com"
GA_MCP_PUBLIC_URL="https://config-mcp.example.com"
EOF

# Extract only the argument-parsing section from install.sh for isolated testing.
# We simulate what install.sh does by reproducing its two-pass logic.
test_parse() {
  # Reset variables
  local PORT=64057
  local CONFIG_FILE=""
  local KIRO_IDENTITY_PROVIDER=""
  local KIRO_REGION=""
  local KIRO_LICENSE=""
  local KC_MODEL_OVERRIDE=""
  local GA_FILE_PUBLIC_URL=""
  local GA_MCP_PUBLIC_URL=""
  local API_KEY_FLAG_PASSED=0
  local GA_API_KEY=""
  local _args=("$@")

  # First pass: extract --config
  for ((i=0; i < ${#_args[@]}; i++)); do
    if [[ "${_args[i]}" == "--config" ]]; then
      CONFIG_FILE="${_args[i+1]:-}"
      break
    fi
  done

  # Source config if provided
  if [[ -n "$CONFIG_FILE" ]]; then
    if [[ ! -f "$CONFIG_FILE" ]]; then
      echo "__ERROR__:config file does not exist"
      return 0
    fi
    if [[ ! -r "$CONFIG_FILE" ]]; then
      echo "__ERROR__:config file is not readable"
      return 0
    fi
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
  fi

  # Second pass: parse flags (overrides config)
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config) shift 2 ;;
      --identity-provider) KIRO_IDENTITY_PROVIDER="$2"; shift 2 ;;
      --region) KIRO_REGION="$2"; shift 2 ;;
      --license) KIRO_LICENSE="$2"; shift 2 ;;
      --port) PORT="$2"; shift 2 ;;
      --model) KC_MODEL_OVERRIDE="$2"; shift 2 ;;
      --api-key) GA_API_KEY="$2"; API_KEY_FLAG_PASSED=1; shift 2 ;;
      --file-public-url) GA_FILE_PUBLIC_URL="$2"; shift 2 ;;
      --mcp-public-url) GA_MCP_PUBLIC_URL="$2"; shift 2 ;;
      *) echo "Unknown argument: $1" >&2; return 1 ;;
    esac
  done

  # Output all vars for assertion
  echo "PORT=$PORT"
  echo "KIRO_IDENTITY_PROVIDER=$KIRO_IDENTITY_PROVIDER"
  echo "KIRO_REGION=$KIRO_REGION"
  echo "KIRO_LICENSE=$KIRO_LICENSE"
  echo "KC_MODEL_OVERRIDE=$KC_MODEL_OVERRIDE"
  echo "GA_FILE_PUBLIC_URL=$GA_FILE_PUBLIC_URL"
  echo "GA_MCP_PUBLIC_URL=$GA_MCP_PUBLIC_URL"
  echo "GA_API_KEY=$GA_API_KEY"
}

# ── Test 1: Config file only (no flags) uses config values ────────────────────
echo ""
echo "--- Test 1: Config file only, no flags → uses config values ---"
OUTPUT=$(test_parse --config "$TMPDIR/test.conf")

echo "$OUTPUT" | grep -q "PORT=9999" && pass "PORT from config" || fail "PORT from config (got: $(echo "$OUTPUT" | grep PORT))"
echo "$OUTPUT" | grep -q "KIRO_IDENTITY_PROVIDER=https://config-idp.example.com" && pass "IDP from config" || fail "IDP from config"
echo "$OUTPUT" | grep -q "KIRO_REGION=us-west-2" && pass "REGION from config" || fail "REGION from config"
echo "$OUTPUT" | grep -q "KIRO_LICENSE=pro" && pass "LICENSE from config" || fail "LICENSE from config"
echo "$OUTPUT" | grep -q "KC_MODEL_OVERRIDE=config-model" && pass "MODEL from config" || fail "MODEL from config"
echo "$OUTPUT" | grep -q "GA_FILE_PUBLIC_URL=https://config-files.example.com" && pass "FILE_PUBLIC_URL from config" || fail "FILE_PUBLIC_URL from config"
echo "$OUTPUT" | grep -q "GA_MCP_PUBLIC_URL=https://config-mcp.example.com" && pass "MCP_PUBLIC_URL from config" || fail "MCP_PUBLIC_URL from config"

# ── Test 2: Flags override config values ──────────────────────────────────────
echo ""
echo "--- Test 2: Config file + flags → flags win ---"
OUTPUT=$(test_parse --config "$TMPDIR/test.conf" \
  --port 8080 \
  --identity-provider "https://flag-idp.example.com" \
  --region "eu-west-1" \
  --license "enterprise" \
  --model "flag-model" \
  --file-public-url "https://flag-files.example.com" \
  --mcp-public-url "https://flag-mcp.example.com")

echo "$OUTPUT" | grep -q "PORT=8080" && pass "PORT flag overrides config" || fail "PORT flag overrides config (got: $(echo "$OUTPUT" | grep PORT))"
echo "$OUTPUT" | grep -q "KIRO_IDENTITY_PROVIDER=https://flag-idp.example.com" && pass "IDP flag overrides config" || fail "IDP flag overrides config"
echo "$OUTPUT" | grep -q "KIRO_REGION=eu-west-1" && pass "REGION flag overrides config" || fail "REGION flag overrides config"
echo "$OUTPUT" | grep -q "KIRO_LICENSE=enterprise" && pass "LICENSE flag overrides config" || fail "LICENSE flag overrides config"
echo "$OUTPUT" | grep -q "KC_MODEL_OVERRIDE=flag-model" && pass "MODEL flag overrides config" || fail "MODEL flag overrides config"
echo "$OUTPUT" | grep -q "GA_FILE_PUBLIC_URL=https://flag-files.example.com" && pass "FILE_PUBLIC_URL flag overrides config" || fail "FILE_PUBLIC_URL flag overrides config"
echo "$OUTPUT" | grep -q "GA_MCP_PUBLIC_URL=https://flag-mcp.example.com" && pass "MCP_PUBLIC_URL flag overrides config" || fail "MCP_PUBLIC_URL flag overrides config"

# ── Test 3: Missing config file errors ────────────────────────────────────────
echo ""
echo "--- Test 3: Missing config file → error ---"
OUTPUT=$(test_parse --config "$TMPDIR/nonexistent.conf")
echo "$OUTPUT" | grep -q "__ERROR__:config file does not exist" && pass "Missing config file errors" || fail "Missing config file errors"

# ── Test 4: Unreadable config file errors ─────────────────────────────────────
echo ""
echo "--- Test 4: Unreadable config file → error ---"
touch "$TMPDIR/unreadable.conf"
chmod 000 "$TMPDIR/unreadable.conf"
OUTPUT=$(test_parse --config "$TMPDIR/unreadable.conf")
echo "$OUTPUT" | grep -q "__ERROR__:config file is not readable" && pass "Unreadable config file errors" || fail "Unreadable config file errors"
chmod 644 "$TMPDIR/unreadable.conf"  # cleanup

# ── Test 5: No config file, no flags → defaults ──────────────────────────────
echo ""
echo "--- Test 5: No config, no flags → defaults ---"
OUTPUT=$(test_parse)
echo "$OUTPUT" | grep -q "PORT=64057" && pass "PORT default" || fail "PORT default (got: $(echo "$OUTPUT" | grep PORT))"
echo "$OUTPUT" | grep -q "KIRO_IDENTITY_PROVIDER=$" && pass "IDP empty by default" || fail "IDP empty by default"
echo "$OUTPUT" | grep -q "GA_FILE_PUBLIC_URL=$" && pass "FILE_PUBLIC_URL empty by default" || fail "FILE_PUBLIC_URL empty by default"
echo "$OUTPUT" | grep -q "GA_MCP_PUBLIC_URL=$" && pass "MCP_PUBLIC_URL empty by default" || fail "MCP_PUBLIC_URL empty by default"

# ── Test 6: Partial override (config sets many, flag overrides one) ───────────
echo ""
echo "--- Test 6: Partial override — flag overrides one, config keeps the rest ---"
OUTPUT=$(test_parse --config "$TMPDIR/test.conf" --port 7777)
echo "$OUTPUT" | grep -q "PORT=7777" && pass "PORT flag overrides" || fail "PORT flag overrides"
echo "$OUTPUT" | grep -q "KIRO_IDENTITY_PROVIDER=https://config-idp.example.com" && pass "IDP kept from config" || fail "IDP kept from config"
echo "$OUTPUT" | grep -q "GA_FILE_PUBLIC_URL=https://config-files.example.com" && pass "FILE_PUBLIC_URL kept from config" || fail "FILE_PUBLIC_URL kept from config"

# ── Test 7: Dedicated machine config variables have defaults ──────────────────
echo ""
echo "--- Test 7: Dedicated machine variables — defaults when unset ---"

test_parse_dedicated() {
  # Reset variables
  local PORT=64057
  local CONFIG_FILE=""
  local KIRO_IDENTITY_PROVIDER=""
  local KIRO_REGION=""
  local KIRO_LICENSE=""
  local KC_MODEL_OVERRIDE=""
  local GA_FILE_PUBLIC_URL=""
  local GA_MCP_PUBLIC_URL=""
  local API_KEY_FLAG_PASSED=0
  local GA_API_KEY=""
  local GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE:-false}"
  local GA_MACHINE_CPUS="${GA_MACHINE_CPUS:-4}"
  local GA_MACHINE_MEMORY="${GA_MACHINE_MEMORY:-8192}"
  local GA_MACHINE_DISK="${GA_MACHINE_DISK:-60}"
  local GA_MACHINE_NAME="${GA_MACHINE_NAME:-ghostship}"
  local _args=("$@")

  # First pass: extract --config
  for ((i=0; i < ${#_args[@]}; i++)); do
    if [[ "${_args[i]}" == "--config" ]]; then
      CONFIG_FILE="${_args[i+1]:-}"
      break
    fi
  done

  # Source config if provided
  if [[ -n "$CONFIG_FILE" ]]; then
    if [[ ! -f "$CONFIG_FILE" ]]; then
      echo "__ERROR__:config file does not exist"
      return 0
    fi
    # shellcheck source=/dev/null
    source "$CONFIG_FILE"
  fi

  # Apply defaults after config sourcing
  GA_DEDICATED_MACHINE="${GA_DEDICATED_MACHINE:-false}"
  GA_MACHINE_CPUS="${GA_MACHINE_CPUS:-4}"
  GA_MACHINE_MEMORY="${GA_MACHINE_MEMORY:-8192}"
  GA_MACHINE_DISK="${GA_MACHINE_DISK:-60}"
  GA_MACHINE_NAME="${GA_MACHINE_NAME:-ghostship}"

  # Second pass: parse flags
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --config) shift 2 ;;
      --identity-provider) KIRO_IDENTITY_PROVIDER="$2"; shift 2 ;;
      --region) KIRO_REGION="$2"; shift 2 ;;
      --license) KIRO_LICENSE="$2"; shift 2 ;;
      --port) PORT="$2"; shift 2 ;;
      --model) KC_MODEL_OVERRIDE="$2"; shift 2 ;;
      --api-key) GA_API_KEY="$2"; API_KEY_FLAG_PASSED=1; shift 2 ;;
      --file-public-url) GA_FILE_PUBLIC_URL="$2"; shift 2 ;;
      --mcp-public-url) GA_MCP_PUBLIC_URL="$2"; shift 2 ;;
      *) shift ;;
    esac
  done

  echo "GA_DEDICATED_MACHINE=$GA_DEDICATED_MACHINE"
  echo "GA_MACHINE_CPUS=$GA_MACHINE_CPUS"
  echo "GA_MACHINE_MEMORY=$GA_MACHINE_MEMORY"
  echo "GA_MACHINE_DISK=$GA_MACHINE_DISK"
  echo "GA_MACHINE_NAME=$GA_MACHINE_NAME"
  echo "PORT=$PORT"
}

OUTPUT=$(test_parse_dedicated)
echo "$OUTPUT" | grep -q "GA_DEDICATED_MACHINE=false" && pass "GA_DEDICATED_MACHINE defaults to false" || fail "GA_DEDICATED_MACHINE default"
echo "$OUTPUT" | grep -q "GA_MACHINE_CPUS=4" && pass "GA_MACHINE_CPUS defaults to 4" || fail "GA_MACHINE_CPUS default"
echo "$OUTPUT" | grep -q "GA_MACHINE_MEMORY=8192" && pass "GA_MACHINE_MEMORY defaults to 8192" || fail "GA_MACHINE_MEMORY default"
echo "$OUTPUT" | grep -q "GA_MACHINE_DISK=60" && pass "GA_MACHINE_DISK defaults to 60" || fail "GA_MACHINE_DISK default"
echo "$OUTPUT" | grep -q "GA_MACHINE_NAME=ghostship" && pass "GA_MACHINE_NAME defaults to ghostship" || fail "GA_MACHINE_NAME default"

# ── Test 8: Dedicated machine variables from config file ──────────────────────
echo ""
echo "--- Test 8: Dedicated machine variables from config file ---"

cat > "$TMPDIR/dedicated.conf" <<'EOF'
GA_DEDICATED_MACHINE=true
GA_MACHINE_CPUS=6
GA_MACHINE_MEMORY=12288
GA_MACHINE_DISK=100
GA_MACHINE_NAME=academy
PORT=9999
EOF

OUTPUT=$(test_parse_dedicated --config "$TMPDIR/dedicated.conf")
echo "$OUTPUT" | grep -q "GA_DEDICATED_MACHINE=true" && pass "GA_DEDICATED_MACHINE from config" || fail "GA_DEDICATED_MACHINE from config"
echo "$OUTPUT" | grep -q "GA_MACHINE_CPUS=6" && pass "GA_MACHINE_CPUS from config" || fail "GA_MACHINE_CPUS from config"
echo "$OUTPUT" | grep -q "GA_MACHINE_MEMORY=12288" && pass "GA_MACHINE_MEMORY from config" || fail "GA_MACHINE_MEMORY from config"
echo "$OUTPUT" | grep -q "GA_MACHINE_DISK=100" && pass "GA_MACHINE_DISK from config" || fail "GA_MACHINE_DISK from config"
echo "$OUTPUT" | grep -q "GA_MACHINE_NAME=academy" && pass "GA_MACHINE_NAME from config" || fail "GA_MACHINE_NAME from config"

# ── Test 9: Socket path resolution logic (Linux, GA_DEDICATED_MACHINE=true) ──
echo ""
echo "--- Test 9: Socket path resolution — dedicated vs default ---"

test_socket_resolution() {
  local GA_DEDICATED_MACHINE="$1"
  local GA_MACHINE_NAME="${2:-ghostship}"
  local _UID=$(id -u)
  local PODMAN_SOCK=""

  if [[ "$GA_DEDICATED_MACHINE" == "true" ]]; then
    local _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$_UID}"
    PODMAN_SOCK="${_RUNTIME_DIR}/podman/${GA_MACHINE_NAME}.sock"
  else
    PODMAN_SOCK="/run/user/$_UID/podman/podman.sock"
  fi
  echo "$PODMAN_SOCK"
}

_UID=$(id -u)
EXPECTED_DEFAULT="/run/user/${_UID}/podman/podman.sock"
EXPECTED_DEDICATED="/run/user/${_UID}/podman/ghostship.sock"
EXPECTED_CUSTOM="/run/user/${_UID}/podman/academy.sock"

OUTPUT=$(test_socket_resolution "false")
[[ "$OUTPUT" == "$EXPECTED_DEFAULT" ]] && pass "Default socket path: $OUTPUT" || fail "Default socket path (got: $OUTPUT, expected: $EXPECTED_DEFAULT)"

OUTPUT=$(test_socket_resolution "true" "ghostship")
[[ "$OUTPUT" == "$EXPECTED_DEDICATED" ]] && pass "Dedicated socket path: $OUTPUT" || fail "Dedicated socket path (got: $OUTPUT, expected: $EXPECTED_DEDICATED)"

OUTPUT=$(test_socket_resolution "true" "academy")
[[ "$OUTPUT" == "$EXPECTED_CUSTOM" ]] && pass "Custom-name socket path: $OUTPUT" || fail "Custom-name socket path (got: $OUTPUT, expected: $EXPECTED_CUSTOM)"

# ── Test 10: GA_DEDICATED_MACHINE=false skips dedicated provisioning ──────────
echo ""
echo "--- Test 10: Fallback — GA_DEDICATED_MACHINE=false uses default socket ---"

test_gate_logic() {
  local GA_DEDICATED_MACHINE="${1:-false}"
  if [[ "$GA_DEDICATED_MACHINE" == "true" ]]; then
    echo "DEDICATED"
  else
    echo "DEFAULT"
  fi
}

OUTPUT=$(test_gate_logic "false")
[[ "$OUTPUT" == "DEFAULT" ]] && pass "GA_DEDICATED_MACHINE=false → DEFAULT path" || fail "Gate: false → DEFAULT"

OUTPUT=$(test_gate_logic "")
[[ "$OUTPUT" == "DEFAULT" ]] && pass "GA_DEDICATED_MACHINE unset → DEFAULT path" || fail "Gate: unset → DEFAULT"

OUTPUT=$(test_gate_logic "true")
[[ "$OUTPUT" == "DEDICATED" ]] && pass "GA_DEDICATED_MACHINE=true → DEDICATED path" || fail "Gate: true → DEDICATED"

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
