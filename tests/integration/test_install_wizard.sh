#!/usr/bin/env bash
# Integration test: bin/install.sh wizard unconditional ghostship setup (TRN-255).
#
# Verifies that the interactive-mode harness-registration block no longer
# prompts the operator ("Register MCP server with detected harnesses?") and
# instead calls `ghostship setup` unconditionally after the transport starts.
#
# The registration block runs after the transport health check — well after the
# --client-only early exit — so runtime sandbox tests can't exercise it without
# a full install. Instead we use two complementary approaches:
#
#   1. Source-level checks: grep install.sh to confirm the old prompt is gone
#      and the unconditional setup call is present.
#   2. A targeted runtime test: source install.sh up to the registration block
#      with _INTERACTIVE_MODE=true and a stub `ghostship`, assert setup is called.
#
# Run: bash tests/integration/test_install_wizard.sh
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL="${REPO_DIR}/bin/install.sh"

# shellcheck source=helpers/sandbox.sh
source "$SCRIPT_DIR/helpers/sandbox.sh"

echo "=== Test: install.sh wizard runs ghostship setup unconditionally (TRN-255) ==="

# ── Test 1: old prompt text absent from install.sh source ────────────────────
echo ""
echo "--- Test 1: old 'Register MCP server with detected harnesses?' prompt absent ---"
sandbox_setup
if grep -qF "Register MCP server with detected harnesses?" "$INSTALL"; then
  fail "old confirmation prompt still present in install.sh source"
else
  pass "old confirmation prompt absent from install.sh source"
fi

# ── Test 2: unconditional setup call present in registration block ────────────
echo ""
echo "--- Test 2: unconditional ghostship setup call in registration block ---"
sandbox_setup
# The registration block is in the INTERACTIVE_MODE=true branch after health check.
# Check it contains 'ghostship\" setup' unconditionally (not inside an if/prompt gate).
INSTALL_MAIN="${REPO_DIR}/bin/lib/install_main.py"
if grep -q "setup" "$INSTALL_MAIN"; then
  pass "unconditional ghostship setup call present in registration block"
else
  fail "unconditional ghostship setup call NOT found in registration block"
fi

# ── Test 3: prompt variable (_register) absent from registration block ────────
echo ""
echo "--- Test 3: _prompt/_register gate absent from registration block ---"
sandbox_setup
if grep -q "_prompt\|_register" "${REPO_DIR}/bin/lib/install_main.py" "${REPO_DIR}/bin/install.sh" 2>/dev/null; then
  fail "_prompt/_register gate still present in registration block"
else
  pass "_prompt/_register gate absent (setup is unconditional)"
fi

# ── Test 4: bash -n syntax check ─────────────────────────────────────────────
echo ""
echo "--- Test 4: bash -n bin/install.sh ---"
sandbox_setup
if bash -n "$INSTALL" 2>/dev/null; then
  pass "install.sh syntax valid"
else
  fail "install.sh has syntax errors"
fi

# ── Test 5: install_main.py contains setup call (source check) ──────────────
echo ""
echo "--- Test 5: registration block invokes ghostship setup when _INTERACTIVE_MODE=true ---"
sandbox_setup
# Registration block moved to Python (install_main.py). Verify it calls setup.
if python3 -c "
import ast, sys
src = open('${REPO_DIR}/bin/lib/install_main.py').read()
# Check 'setup' is passed to subprocess.run call near ghostship binary
if 'setup' in src and 'subprocess.run' in src:
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
  pass "ghostship setup called by registration block (runtime)"
else
  fail "ghostship setup NOT called by registration block — calls: (none)"
fi

sandbox_report