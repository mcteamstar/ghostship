#!/usr/bin/env bash
# Integration test: scripts/install.sh flag parsing + config sourcing.
#
# trn-212-test-coverage-gaps A.2 — this file was rewritten to call the REAL
# scripts/install.sh inside a sandbox (see helpers/sandbox.sh) instead of
# reimplementing the parser. Flag drift between the test and the script is now
# impossible: every case runs the actual argument-parsing loop.
#
# Lever: --client-only makes install.sh exit 0 right after flag parsing and
# config sourcing (it wires the CLI via `ghostship setup` under the sandbox
# HOME and skips ALL container-infrastructure steps). So every flag the parser
# accepts is exercised, and an unknown flag still aborts the script non-zero.
#
# Run: bash tests/integration/test_install_config.sh
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL="$REPO_DIR/scripts/install.sh"
URL="http://localhost:64057/mcp"

# shellcheck source=helpers/sandbox.sh
source "$SCRIPT_DIR/helpers/sandbox.sh"

echo "=== Test: install.sh flag parsing (real script, sandboxed) ==="

# ── 1. Known flags are accepted (parser does not reject them) ────────────────
# Each known flag is passed alongside --client-only so the script parses it and
# exits 0 via the client-only path. "Unknown argument" in the output means the
# parser rejected the flag — a drift regression.
echo ""
echo "--- Known flags are accepted ---"

# Flags that take a value, each with a sample value.
declare -a KNOWN_VALUE_FLAGS=(
  "--identity-provider https://idp.example.com"
  "--region us-west-2"
  "--license pro"
  "--port 55000"
  "--model some-model"
  "--model-default some-default-model"
  "--public-url https://public.example.com"
  "--api-key secret-key"
  "--caddy-domain portal.example.com"
  "--caddy-tls-mode off"
)

for spec in "${KNOWN_VALUE_FLAGS[@]}"; do
  sandbox_setup
  # shellcheck disable=SC2086
  sandbox_run_script "$INSTALL" --client-only --url "$URL" $spec
  flag="${spec%% *}"
  if [[ "$SANDBOX_STATUS" -eq 0 ]] && ! sandbox_output_contains "Unknown argument"; then
    pass "install.sh accepts ${flag}"
  else
    fail "install.sh rejected ${flag} (status=${SANDBOX_STATUS})"
    echo "    output: ${SANDBOX_OUTPUT}"
  fi
done

# --config is accepted and sources values from the file.
sandbox_setup
CONF="${SANDBOX_DIR}/test.conf"
cat > "$CONF" <<'EOF'
PORT=9999
KIRO_IDENTITY_PROVIDER="https://config-idp.example.com"
KIRO_REGION="us-west-2"
KIRO_LICENSE="pro"
EOF
sandbox_run_script "$INSTALL" --config "$CONF" --client-only --url "$URL"
if [[ "$SANDBOX_STATUS" -eq 0 ]] && sandbox_output_contains "Sourced config file"; then
  pass "install.sh accepts --config and sources it"
else
  fail "install.sh did not source --config (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── 2. Removed flags are rejected as unknown (regression guard) ──────────────
# --file-public-url and --mcp-public-url were removed. If they are ever
# re-added without updating this guard, the test turns red.
echo ""
echo "--- Removed flags are rejected ---"

for bad in --file-public-url --mcp-public-url; do
  sandbox_setup
  sandbox_run_script "$INSTALL" --client-only --url "$URL" "$bad" http://x
  if [[ "$SANDBOX_STATUS" -ne 0 ]] && sandbox_output_contains "Unknown argument: ${bad}"; then
    pass "install.sh rejects removed flag ${bad}"
  else
    fail "install.sh did NOT reject ${bad} (status=${SANDBOX_STATUS})"
    echo "    output: ${SANDBOX_OUTPUT}"
  fi
done

# A clearly bogus flag is also rejected.
sandbox_setup
sandbox_run_script "$INSTALL" --client-only --url "$URL" --totally-bogus-flag
if [[ "$SANDBOX_STATUS" -ne 0 ]] && sandbox_output_contains "Unknown argument: --totally-bogus-flag"; then
  pass "install.sh rejects an arbitrary unknown flag"
else
  fail "install.sh did NOT reject --totally-bogus-flag (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── 3. Validation error paths ────────────────────────────────────────────────
echo ""
echo "--- Validation error paths ---"

# A value-taking flag with no value aborts with a clear error.
sandbox_setup
sandbox_run_script "$INSTALL" --client-only --url "$URL" --port
if [[ "$SANDBOX_STATUS" -ne 0 ]] && sandbox_output_contains "--port requires a value"; then
  pass "install.sh errors when --port has no value"
else
  fail "install.sh did not error on missing --port value (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# An unknown --caddy-tls-mode value is rejected (validation runs before the
# client-only exit).
sandbox_setup
sandbox_run_script "$INSTALL" --client-only --url "$URL" --caddy-tls-mode bogus
if [[ "$SANDBOX_STATUS" -ne 0 ]] && sandbox_output_contains "is not one of"; then
  pass "install.sh rejects an invalid --caddy-tls-mode value"
else
  fail "install.sh did not reject invalid --caddy-tls-mode (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# A nonexistent --config path aborts with the documented error.
sandbox_setup
sandbox_run_script "$INSTALL" --config "${SANDBOX_DIR}/does-not-exist.conf" --client-only --url "$URL"
if [[ "$SANDBOX_STATUS" -ne 0 ]] && sandbox_output_contains "config file does not exist"; then
  pass "install.sh errors on a nonexistent --config path"
else
  fail "install.sh did not error on a missing config file (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

sandbox_report
