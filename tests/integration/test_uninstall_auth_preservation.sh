#!/usr/bin/env bash
# Integration test: bin/uninstall.sh credential + machine preservation.
#
# trn-212-test-coverage-gaps A.3/A.4 — rewritten to invoke the REAL
# bin/uninstall.sh --yes inside a sandbox (helpers/sandbox.sh) instead of a
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
UNINSTALL="$REPO_DIR/bin/uninstall.sh"
MACHINE="ghost-academy"   # install.sh/uninstall.sh default GA_MACHINE_NAME

# shellcheck source=helpers/sandbox.sh
source "$SCRIPT_DIR/helpers/sandbox.sh"

# Seed a realistic dedicated-instance layout inside the current sandbox HOME.
# Pass "unit" as $1 to also create the systemd unit file that makes
# uninstall.sh treat this as a dedicated machine (so the containers-teardown
# branch runs).
#
# TRN-253/TRN-233: the per-launch credential store (credentials/) is the thing
# an uninstall must preserve by default; the legacy ga-kiro-auth file was
# removed in TRN-233. We seed credentials/ and assert on that.
seed_instance() {
  local with_unit="${1:-}"
  local data_dir="${SANDBOX_HOME}/.local/share/${MACHINE}/data"
  local containers_dir="${SANDBOX_HOME}/.local/share/${MACHINE}/containers"
  mkdir -p "${containers_dir}/storage/overlay"
  mkdir -p "${data_dir}/credentials"
  echo '{"backend":"kiro"}' > "${data_dir}/credentials/kiro.json"
  echo "fake-crews"         > "${data_dir}/crews.json"
  if [[ "$with_unit" == "unit" ]]; then
    mkdir -p "${SANDBOX_HOME}/.config/systemd/user"
    : > "${SANDBOX_HOME}/.config/systemd/user/podman-${MACHINE}.service"
  fi
}

# Paths inside the current sandbox (recomputed after each sandbox_setup).
creds_dir()      { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/data/credentials"; }
creds_file()     { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/data/credentials/kiro.json"; }
crews_file()     { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/data/crews.json"; }
containers_dir() { echo "${SANDBOX_HOME}/.local/share/${MACHINE}/containers"; }

echo "=== Test: uninstall.sh credentials / machine preservation (real script) ==="

# ── Test 1: no --purge-auth → credentials/ survives ──────────────────────────
echo ""
echo "--- Test 1: credentials/ preserved without --purge-auth ---"
sandbox_setup
seed_instance unit
sandbox_run_script "$UNINSTALL" --yes
if [[ -f "$(creds_file)" ]]; then
  pass "credentials/ preserved without --purge-auth"
else
  fail "credentials/ was destroyed without --purge-auth"
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
# Credentials still survive too (no --purge-auth).
if [[ -f "$(creds_file)" ]]; then
  pass "credentials/ preserved with --keep-machine"
else
  fail "credentials/ destroyed with --keep-machine"
fi

# ── Test 3: --purge-auth removes credentials/ (A.4 regression) ────────────────
echo ""
echo "--- Test 3: --purge-auth removes credentials/ ---"
sandbox_setup
seed_instance unit
sandbox_run_script "$UNINSTALL" --yes --purge-auth
if [[ ! -e "$(creds_dir)" ]]; then
  pass "credentials/ removed by --purge-auth"
else
  fail "credentials/ survived --purge-auth"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── Test 4: data dir cleanup without a dedicated machine ──────────────────────
# No systemd unit seeded → the dedicated-machine teardown branch is skipped,
# but the data-dir cleanup still runs and still preserves credentials/.
echo ""
echo "--- Test 4: data-dir cleanup with no dedicated machine ---"
sandbox_setup
seed_instance   # no unit
sandbox_run_script "$UNINSTALL" --yes
if [[ -f "$(creds_file)" && ! -f "$(crews_file)" ]]; then
  pass "data dir cleaned, credentials/ preserved (no dedicated machine)"
else
  fail "data-dir cleanup incorrect without a dedicated machine"
  echo "    creds exists: $([[ -f "$(creds_file)" ]] && echo yes || echo no); crews exists: $([[ -f "$(crews_file)" ]] && echo yes || echo no)"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── Test 5: multi-profile layout (TRN-252) is preserved without --purge-auth ──
# After TRN-252 the credential store uses credentials/<backend>/<profile>.json.
# Uninstall.sh preserves the entire credentials/ directory by excluding it from
# the data-dir wipe; verify that the new sub-directory layout survives too.
echo ""
echo "--- Test 5: multi-profile layout preserved without --purge-auth ---"
sandbox_setup
# Seed the new per-profile layout with two profiles.
_CREDS="${SANDBOX_HOME}/.local/share/${MACHINE}/data/credentials"
mkdir -p "${_CREDS}/kiro"
echo '{"backend":"kiro","method":"api-key","stored_at":"t","provider":null,"payload":""}' \
  > "${_CREDS}/kiro/default.json"
echo '{"backend":"kiro","method":"api-key","stored_at":"t","provider":null,"payload":""}' \
  > "${_CREDS}/kiro/corp.json"
echo "fake-crews" > "${SANDBOX_HOME}/.local/share/${MACHINE}/data/crews.json"
sandbox_run_script "$UNINSTALL" --yes
if [[ -f "${_CREDS}/kiro/default.json" && -f "${_CREDS}/kiro/corp.json" ]]; then
  pass "multi-profile credentials/ preserved without --purge-auth"
else
  fail "multi-profile credentials/ was destroyed without --purge-auth"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── Test 6: multi-profile layout removed by --purge-auth ──────────────────────
echo ""
echo "--- Test 6: multi-profile layout removed by --purge-auth ---"
sandbox_setup
_CREDS="${SANDBOX_HOME}/.local/share/${MACHINE}/data/credentials"
mkdir -p "${_CREDS}/kiro" "${_CREDS}/claude"
echo '{}' > "${_CREDS}/kiro/default.json"
echo '{}' > "${_CREDS}/kiro/corp.json"
echo '{}' > "${_CREDS}/claude/default.json"
sandbox_run_script "$UNINSTALL" --yes --purge-auth
if [[ ! -d "${_CREDS}" ]]; then
  pass "multi-profile credentials/ tree removed by --purge-auth"
else
  fail "multi-profile credentials/ survived --purge-auth"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

sandbox_report
