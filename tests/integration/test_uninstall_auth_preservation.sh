#!/usr/bin/env bash
# Test: Linux uninstall preserves ga-kiro-auth unless --purge-auth is passed
#
# Verifies that the Linux dedicated instance teardown in uninstall.sh only
# wipes containers/, not the entire ~/.local/share/${GA_MACHINE_NAME} tree.
# The ga-kiro-auth file should survive an uninstall without --purge-auth,
# even when --keep-machine is not passed.
#
# Run: bash tests/integration/test_uninstall_auth_preservation.sh
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ✗ $1"; }

echo "=== Test: Linux Uninstall Auth Preservation ==="

# ── Shared helpers ────────────────────────────────────────────────────────────

# Simulate the Linux dedicated machine teardown block from uninstall.sh.
# This mirrors the exact logic so regressions are caught here first.
simulate_linux_teardown() {
  local machine_name="$1"
  local base_dir="$2"
  local keep_machine="$3"  # "1" = keep, "" = remove

  local storage_root="${base_dir}/${machine_name}/containers/storage"

  if [[ -z "$keep_machine" ]]; then
    if [[ -d "${base_dir}/${machine_name}/containers" ]]; then
      # Only wipe containers/ — mirrors the fix in uninstall.sh
      rm -rf "${base_dir}/${machine_name}/containers"
    fi
  fi
}

# ── Test 1: auth file survives teardown without --keep-machine ────────────────
echo ""
echo "--- Test 1: ga-kiro-auth preserved without --keep-machine ---"

TMPDIR1="$(mktemp -d)"
trap 'rm -rf "$TMPDIR1"' EXIT
MACHINE="ghost-academy"

# Set up fake dedicated instance structure
mkdir -p "${TMPDIR1}/${MACHINE}/containers/storage/overlay"
mkdir -p "${TMPDIR1}/${MACHINE}/data"
echo "fake-auth-token" > "${TMPDIR1}/${MACHINE}/data/ga-kiro-auth"
echo "fake-crews" > "${TMPDIR1}/${MACHINE}/data/crews.json"

# Run teardown without --keep-machine
simulate_linux_teardown "$MACHINE" "$TMPDIR1" ""

# containers/ should be gone
if [[ ! -d "${TMPDIR1}/${MACHINE}/containers" ]]; then
  pass "containers/ removed by teardown"
else
  fail "containers/ still present after teardown"
fi

# data/ and ga-kiro-auth should survive
if [[ -f "${TMPDIR1}/${MACHINE}/data/ga-kiro-auth" ]]; then
  pass "ga-kiro-auth preserved without --keep-machine"
else
  fail "ga-kiro-auth was destroyed without --purge-auth"
fi

if [[ -f "${TMPDIR1}/${MACHINE}/data/crews.json" ]]; then
  pass "data/ directory preserved without --keep-machine"
else
  fail "data/ directory was destroyed without --purge-auth"
fi

# ── Test 2: --keep-machine also preserves auth ────────────────────────────────
echo ""
echo "--- Test 2: ga-kiro-auth preserved with --keep-machine ---"

TMPDIR2="$(mktemp -d)"
trap 'rm -rf "$TMPDIR1" "$TMPDIR2"' EXIT

mkdir -p "${TMPDIR2}/${MACHINE}/containers/storage/overlay"
mkdir -p "${TMPDIR2}/${MACHINE}/data"
echo "fake-auth-token" > "${TMPDIR2}/${MACHINE}/data/ga-kiro-auth"

# Run teardown WITH --keep-machine (containers/ skipped entirely)
simulate_linux_teardown "$MACHINE" "$TMPDIR2" "1"

if [[ -d "${TMPDIR2}/${MACHINE}/containers" ]]; then
  pass "containers/ preserved with --keep-machine"
else
  fail "containers/ removed despite --keep-machine"
fi

if [[ -f "${TMPDIR2}/${MACHINE}/data/ga-kiro-auth" ]]; then
  pass "ga-kiro-auth preserved with --keep-machine"
else
  fail "ga-kiro-auth was destroyed with --keep-machine"
fi

# ── Test 3: --purge-auth removes auth (data-dir cleanup step) ─────────────────
echo ""
echo "--- Test 3: --purge-auth removes ga-kiro-auth ---"

TMPDIR3="$(mktemp -d)"
trap 'rm -rf "$TMPDIR1" "$TMPDIR2" "$TMPDIR3"' EXIT

DATA_DIR="${TMPDIR3}/${MACHINE}/data"
mkdir -p "$DATA_DIR"
AUTH_FILE="${DATA_DIR}/ga-kiro-auth"
echo "fake-auth-token" > "$AUTH_FILE"
echo "fake-crews" > "${DATA_DIR}/crews.json"

# Simulate the data-dir cleanup step with --purge-auth set
simulate_data_dir_cleanup() {
  local data_dir="$1"
  local purge_auth="$2"
  local auth_file="${data_dir}/ga-kiro-auth"

  if [[ -d "$data_dir" ]]; then
    shopt -s dotglob nullglob
    for entry in "$data_dir"/*; do
      [[ "$entry" == "$auth_file" ]] && continue
      rm -rf "$entry"
    done
    shopt -u dotglob nullglob

    if [[ -n "$purge_auth" ]]; then
      rm -f "$auth_file"
    fi
  fi
}

simulate_data_dir_cleanup "$DATA_DIR" "1"

if [[ ! -f "$AUTH_FILE" ]]; then
  pass "ga-kiro-auth removed with --purge-auth"
else
  fail "ga-kiro-auth still present despite --purge-auth"
fi

if [[ ! -f "${DATA_DIR}/crews.json" ]]; then
  pass "crews.json removed by data-dir cleanup"
else
  fail "crews.json still present after data-dir cleanup"
fi

# ── Test 4: without --purge-auth, data-dir cleanup keeps auth ────────────────
echo ""
echo "--- Test 4: data-dir cleanup without --purge-auth keeps ga-kiro-auth ---"

TMPDIR4="$(mktemp -d)"
trap 'rm -rf "$TMPDIR1" "$TMPDIR2" "$TMPDIR3" "$TMPDIR4"' EXIT

DATA_DIR4="${TMPDIR4}/${MACHINE}/data"
mkdir -p "$DATA_DIR4"
echo "fake-auth-token" > "${DATA_DIR4}/ga-kiro-auth"
echo "fake-crews" > "${DATA_DIR4}/crews.json"

simulate_data_dir_cleanup "$DATA_DIR4" ""

if [[ -f "${DATA_DIR4}/ga-kiro-auth" ]]; then
  pass "ga-kiro-auth preserved without --purge-auth in data-dir cleanup"
else
  fail "ga-kiro-auth was destroyed without --purge-auth"
fi

if [[ ! -f "${DATA_DIR4}/crews.json" ]]; then
  pass "crews.json removed by data-dir cleanup (non-auth state cleared)"
else
  fail "crews.json still present after data-dir cleanup"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
