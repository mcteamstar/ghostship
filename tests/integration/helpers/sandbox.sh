#!/usr/bin/env bash
# Shared sandbox harness for the install/uninstall shell integration tests
# (trn-212-test-coverage-gaps, design.md D1).
#
# These helpers let a test invoke the REAL scripts/install.sh and
# scripts/uninstall.sh without touching the host system or needing podman:
#
#   * a tmpdir sandbox with stub `podman` / `podman-compose` / `systemctl` /
#     `id` binaries placed on PATH ahead of the system copies, so the scripts'
#     container/systemd steps become no-ops;
#   * HOME / PREFIX / XDG_DATA_HOME / XDG_RUNTIME_DIR pointed at tmpdir paths so
#     any file the script writes lands inside the sandbox;
#   * unconditional cleanup on EXIT.
#
# Source this file from a test, call `sandbox_setup`, then run the real script
# with `sandbox_run_script`. Flag parsing, config sourcing and the
# validation/error paths run for real — which is the whole point: flag drift
# cannot go undetected because the test calls the real parser.
#
# Usage:
#   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
#   REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
#   # shellcheck source=helpers/sandbox.sh
#   source "$SCRIPT_DIR/helpers/sandbox.sh"
#   sandbox_setup
#   sandbox_run_script "$REPO_DIR/scripts/install.sh" --client-only --url http://x
#   echo "$SANDBOX_STATUS"   # exit code
#   echo "$SANDBOX_OUTPUT"   # combined stdout+stderr

# ── Test-count tracking + pass/fail helpers ──────────────────────────────────
# A test file may `source` this before defining its own pass/fail; define them
# here so every file shares the same reporting and exit convention.
PASS=0
FAIL=0
pass() { PASS=$((PASS + 1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ✗ $1"; }

# Call at the end of a test file: prints the tally and exits non-zero on any
# failure, which is what tests/run.sh keys off.
sandbox_report() {
  echo ""
  echo "Results: ${PASS} passed, ${FAIL} failed"
  [[ "$FAIL" -eq 0 ]]
}

# ── Sandbox lifecycle ─────────────────────────────────────────────────────────

# Create a fresh sandbox and export the isolating environment. Idempotent per
# call: each call makes a NEW tmpdir and registers a cleanup trap for it.
# Exports: SANDBOX_DIR, SANDBOX_BIN, SANDBOX_HOME.
sandbox_setup() {
  SANDBOX_DIR="$(mktemp -d "${TMPDIR:-/tmp}/trn212-sandbox.XXXXXX")"
  SANDBOX_BIN="${SANDBOX_DIR}/bin"
  SANDBOX_HOME="${SANDBOX_DIR}/home"
  mkdir -p "$SANDBOX_BIN" "$SANDBOX_HOME"
  mkdir -p "${SANDBOX_DIR}/data" "${SANDBOX_DIR}/run"

  _sandbox_install_stubs

  # Clean up this sandbox unconditionally on EXIT. Append to any existing trap
  # so multiple sandboxes in one file are all removed.
  trap 'sandbox_teardown' EXIT
}

# Remove every sandbox created in this process.
sandbox_teardown() {
  [[ -n "${SANDBOX_DIR:-}" && -d "$SANDBOX_DIR" ]] && rm -rf "$SANDBOX_DIR"
  return 0
}

# Place stub binaries on PATH. Each stub exits 0 and emits output benign enough
# that the scripts' command-substitution calls (id -u, podman machine ssh …)
# don't fail under `set -e`.
_sandbox_install_stubs() {
  # podman: exit 0 for every subcommand; echo a plausible value for the few
  # calls whose stdout is captured (id -u via `podman machine ssh … id -u`).
  cat > "${SANDBOX_BIN}/podman" <<'STUB'
#!/usr/bin/env bash
# Stub podman — swallow all subcommands. For `machine ssh … -- id -u` and
# `machine ssh … -- id` return a numeric uid so command substitution succeeds.
for arg in "$@"; do
  if [[ "$arg" == "id" ]]; then echo 1000; exit 0; fi
done
exit 0
STUB

  cat > "${SANDBOX_BIN}/podman-compose" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  cat > "${SANDBOX_BIN}/systemctl" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB

  # id: the scripts call `id -u`. Return a fixed uid; pass other forms through
  # to the real id so unrelated calls still behave.
  cat > "${SANDBOX_BIN}/id" <<'STUB'
#!/usr/bin/env bash
if [[ "$1" == "-u" ]]; then echo 1000; exit 0; fi
exec /usr/bin/id "$@"
STUB

  chmod +x "${SANDBOX_BIN}/podman" "${SANDBOX_BIN}/podman-compose" \
    "${SANDBOX_BIN}/systemctl" "${SANDBOX_BIN}/id"
}

# Run a script in the sandboxed environment with a clean env (`env -i`) so no
# ambient HOME/XDG var leaks in. PATH keeps the stub bin first, then the system
# dirs the scripts need (python3 for ghostship, coreutils, bash).
# Captures combined stdout+stderr in SANDBOX_OUTPUT and the exit code in
# SANDBOX_STATUS. Never aborts the caller on a non-zero script exit.
sandbox_run_script() {
  local script="$1"; shift
  set +e
  SANDBOX_OUTPUT="$(
    env -i \
      PATH="${SANDBOX_BIN}:/usr/local/bin:/usr/bin:/bin" \
      HOME="${SANDBOX_HOME}" \
      PREFIX="${SANDBOX_HOME}" \
      XDG_DATA_HOME="${SANDBOX_HOME}/.local/share" \
      XDG_RUNTIME_DIR="${SANDBOX_DIR}/run" \
      bash "$script" "$@" 2>&1
  )"
  SANDBOX_STATUS=$?
  set -e
  return 0
}

# Convenience: assert SANDBOX_OUTPUT contains a substring.
sandbox_output_contains() {
  [[ "$SANDBOX_OUTPUT" == *"$1"* ]]
}
