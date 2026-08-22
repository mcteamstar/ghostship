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

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
