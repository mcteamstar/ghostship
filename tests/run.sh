#!/usr/bin/env bash
# Run the repository's unit, integration, and E2E test categories.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

# ── venv bootstrap ────────────────────────────────────────────────────────────
# Create and activate a local venv with transport deps so tests run consistently
# without polluting the system Python. uv is used when available, else venv+pip.
VENV_DIR="$REPO_DIR/.venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  printf '=== Creating .venv ===\n'
  if command -v uv &>/dev/null; then
    uv venv "$VENV_DIR" --quiet
    uv pip install --quiet --python "$VENV_DIR/bin/python" \
      -r "$REPO_DIR/transport/requirements.txt"
  else
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet -r "$REPO_DIR/transport/requirements.txt"
  fi
fi
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
# ─────────────────────────────────────────────────────────────────────────────

declare -a SELECTED_CATEGORIES=()

if [[ $# -eq 0 ]]; then
  SELECTED_CATEGORIES=(unit integration e2e)
else
  for arg in "$@"; do
    case "$arg" in
      --unit)
        SELECTED_CATEGORIES+=(unit)
        ;;
      --integration)
        SELECTED_CATEGORIES+=(integration)
        ;;
      --e2e)
        SELECTED_CATEGORIES+=(e2e)
        ;;
      --all)
        SELECTED_CATEGORIES=(unit integration e2e)
        ;;
      -h|--help)
        cat <<'USAGE'
Usage: tests/run.sh [--unit] [--integration] [--e2e]

With no flags, all test categories run. Use --all for the same behavior.
USAGE
        exit 0
        ;;
      *)
        printf 'Unknown option: %s\n' "$arg" >&2
        printf 'Usage: %s [--unit] [--integration] [--e2e]\n' "$0" >&2
        exit 2
        ;;
    esac
  done
fi

declare -a CATEGORY_NAMES=()
declare -a CATEGORY_CODES=()
OVERALL_EXIT=0

run_integration() {
  local category_exit=0
  local script script_exit
  for script in \
    "$REPO_DIR/tests/integration/test_install_config.sh" \
    "$REPO_DIR/tests/integration/test_install_cache_detection.sh" \
    "$REPO_DIR/tests/integration/test_dedicated_transport.sh"; do
    printf '\n--- Integration: %s ---\n' "$(basename "$script")"
    if bash "$script"; then
      printf 'Integration script result: PASS (%s)\n' "$(basename "$script")"
    else
      script_exit=$?
      printf 'Integration script result: FAIL (%s, exit %d)\n' \
        "$(basename "$script")" "$script_exit"
      category_exit=1
    fi
  done
  return "$category_exit"
}

run_category() {
  local category="$1"
  shift
  local category_exit=0

  printf '\n=== Running %s tests ===\n' "$category"
  "$@" || category_exit=$?

  CATEGORY_NAMES+=("$category")
  CATEGORY_CODES+=("$category_exit")
  if [[ "$category_exit" -eq 0 ]]; then
    printf 'Category result: %s PASS (exit 0)\n' "$category"
  else
    printf 'Category result: %s FAIL (exit %d)\n' "$category" "$category_exit"
    OVERALL_EXIT=1
  fi
}

for category in "${SELECTED_CATEGORIES[@]}"; do
  case "$category" in
    unit)
      run_category unit \
        python3 -m unittest discover -s tests/unit -p "test_*.py" -t .
      ;;
    integration)
      run_category integration run_integration
      ;;
    e2e)
      if python3 -c "import unittest_parallel" 2>/dev/null; then
        USE_PARALLEL=1
      else
        USE_PARALLEL=0
      fi
      if [[ "$USE_PARALLEL" -eq 1 ]]; then
        run_category e2e \
          python3 -m unittest_parallel -s tests/e2e -p "test_*.py" -t .
      else
        run_category e2e \
          python3 -m unittest discover -s tests/e2e -p "test_*.py" -t .
      fi
      ;;
  esac
done

printf '\n=== Aggregate test summary ===\n'
for ((i = 0; i < ${#CATEGORY_NAMES[@]}; i++)); do
  if [[ "${CATEGORY_CODES[i]}" -eq 0 ]]; then
    printf '%s: PASS\n' "${CATEGORY_NAMES[i]}"
  else
    printf '%s: FAIL (exit %s)\n' \
      "${CATEGORY_NAMES[i]}" "${CATEGORY_CODES[i]}"
  fi
done

if [[ "$OVERALL_EXIT" -eq 0 ]]; then
  printf 'Aggregate result: PASS (%d categories)\n' "${#CATEGORY_NAMES[@]}"
else
  printf 'Aggregate result: FAIL (one or more categories failed)\n'
fi

exit "$OVERALL_EXIT"
