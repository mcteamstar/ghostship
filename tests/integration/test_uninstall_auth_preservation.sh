#!/usr/bin/env bash
# Integration test: scripts/uninstall.sh credential + machine preservation.
#
# trn-212-test-coverage-gaps A.3/A.4 — rewritten to invoke the REAL
# scripts/uninstall.sh --yes inside a sandbox (helpers/sandbox.sh) instead of a
# `simulate_linux_teardown` reimplementation. Assertions are made on actual
# filesystem state after the real script runs, so a regression that deleted
# credentials would turn this test red (the old reimplementation would not).
#
# Linux data-dir layout the script operates on:
#   $XDG_DATA_HOME/$GA_MACHINE_NAME/data/   <- ga-kiro-auth, crews.json, …
#   $HOME/.local/share/$GA_MACHINE_NAME/containers/   <- storage root
# A dedicated-machine teardown only fires when a systemd unit file for the
# machine exists under ~/.config/systemd/user, so we seed one when the scenario
# needs the containers-teardown branch to run.
#
# Run: bash tests/integration/test_uninstall_auth_preservation.sh
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
UNINSTALL="$REPO_DIR/scripts/uninstall.sh"
MACHINE="ghost-academy"   # install.sh/uninstall.sh default GA_MACHINE_NAME

# shellcheck source=helpers/sandbox.sh
source "$SCRIPT_DIR/helpers/sandbox.sh"

# Seed a realistic dedicated-instance layout inside the current sandbox HOME.
# Pass "unit" as $1 to also create the systemd unit file that makes
# uninstall.sh treat this as a dedicated machine (so the containers-teardown
# branch runs).
seed_instance() {
  local with_unit="${1:-}"
  local data_dir="${SANDBOX_HOME}/.local/share/${MACHINE}/data"
  local containers_dir="${SANDBOX_HOME}/.local/share/${MACHINE}/containers"
  mkdir -p "${containers_dir}/storage/overlay"
  mkdir -p "$data_dir"
  echo "fake-auth-token" > "${data_dir}/ga-kiro-auth"
  echo "fake-crews"      > "${data_dir}/crews.json"
  if [[ "$with_unit" == "unit" ]]; then
    mkdir -p "${SANDBOX_HOME}/.config/systemd/user"
    : > "${SANDBOX_HOME}/.config/systemd/user/podman-${MACHINE}.service"
  fi
}

# Paths inside the current sandbox (recomputed after each sandbox_setup).
auth_file()      { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/data/ga-kiro-auth"; }
crews_file()     { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/data/crews.json"; }
containers_dir() { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/containers"; }

echo "=== Test: uninstall.sh auth / machine preservation (real script) ==="

# ── Test 1: no --purge-auth → ga-kiro-auth survives ──────────────────────────
echo ""
echo "--- Test 1: ga-kiro-auth preserved without --purge-auth ---"
sandbox_setup
seed_instance unit
sandbox_run_script "$UNINSTALL" --yes
if [[ -f "$(auth_file)" ]]; then
  pass "ga-kiro-auth preserved without --purge-auth"
else
  fail "ga-kiro-auth was destroyed without --purge-auth"
  echo "    output: ${SANDBOX_OUTPUT}"
fi
if [[ ! -f "$(crews_file)" ]]; then
  pass "non-auth data (crews.json) removed from data dir"
else
  fail "crews.json survived — data dir was not cleaned"
fi

# ── Test 2: --keep-machine → containers storage survives ──────────────────────
echo ""
echo "--- Test 2: --keep-machine preserves containers storage ---"
sandbox_setup
seed_instance unit
sandbox_run_script "$UNINSTALL" --yes --keep-machine
if [[ -d "$(containers_dir)" ]]; then
  pass "containers/ preserved with --keep-machine"
else
  fail "containers/ removed despite --keep-machine"
  echo "    output: ${SANDBOX_OUTPUT}"
fi
# Auth still survives too (no --purge-auth).
if [[ -f "$(auth_file)" ]]; then
  pass "ga-kiro-auth preserved with --keep-machine"
else
  fail "ga-kiro-auth destroyed with --keep-machine"
fi

# ── Test 3: --purge-auth removes ga-kiro-auth (A.4 regression) ────────────────
echo ""
echo "--- Test 3: --purge-auth removes ga-kiro-auth ---"
sandbox_setup
seed_instance unit
sandbox_run_script "$UNINSTALL" --yes --purge-auth
if [[ ! -e "$(auth_file)" ]]; then
  pass "ga-kiro-auth removed by --purge-auth"
else
  fail "ga-kiro-auth survived --purge-auth"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── Test 4: data dir cleanup without a dedicated machine ──────────────────────
# No systemd unit seeded → the dedicated-machine teardown branch is skipped,
# but the data-dir cleanup still runs and still preserves ga-kiro-auth.
echo ""
echo "--- Test 4: data-dir cleanup with no dedicated machine ---"
sandbox_setup
seed_instance   # no unit
sandbox_run_script "$UNINSTALL" --yes
if [[ -f "$(auth_file)" && ! -f "$(crews_file)" ]]; then
  pass "data dir cleaned, ga-kiro-auth preserved (no dedicated machine)"
else
  fail "data-dir cleanup incorrect without a dedicated machine"
  echo "    auth exists: $([[ -f "$(auth_file)" ]] && echo yes || echo no); crews exists: $([[ -f "$(crews_file)" ]] && echo yes || echo no)"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

sandbox_report
