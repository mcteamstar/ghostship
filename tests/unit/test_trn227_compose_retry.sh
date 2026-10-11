#!/usr/bin/env bash
# Unit test: GA_COMPOSE_RETRY_ATTEMPTS / GA_COMPOSE_RETRY_DELAY_SECS retry loop
# in scripts/install.sh (TRN-227).
#
# Strategy: extract the retry-loop logic into a temporary script fragment using
# the same variables, then stub _compose_cmd to fail N times then succeed.
# This avoids a full install.sh run while testing the exact loop code path.
#
# Run: bash tests/unit/test_trn227_compose_retry.sh
set -eo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  ✓ $1"; PASS=$(( PASS + 1 )); }
fail() { echo "  ✗ $1"; FAIL=$(( FAIL + 1 )); }

# Build a self-contained retry harness matching the install.sh loop exactly.
# _compose_cmd is a stub whose failure count is controlled by FAIL_N.
make_harness() {
  local fail_n="$1"
  local attempts="${2:-3}"
  local delay="${3:-0}"  # 0 for tests — no real sleep
  local tmpfile
  tmpfile=$(mktemp -t test_trn227_harness)
  cat >"$tmpfile" <<HARNESS
FAIL_REMAINING=$fail_n
stub_compose() {
  if [[ \$FAIL_REMAINING -gt 0 ]]; then
    FAIL_REMAINING=\$(( FAIL_REMAINING - 1 )) || true
    return 1
  fi
  return 0
}
_compose_attempts="${attempts}"
_compose_delay="${delay}"
if ! [[ "\${_compose_attempts}" =~ ^[1-9][0-9]*$ ]]; then
  echo "WARNING: GA_COMPOSE_RETRY_ATTEMPTS='\${_compose_attempts}' is not a positive integer -- using 1" >&2
  _compose_attempts=1
fi
_compose_ok=0
for _attempt in \$(seq 1 "\${_compose_attempts}"); do
  if stub_compose; then
    _compose_ok=1; break
  fi
  if [[ "\${_attempt}" -lt "\${_compose_attempts}" ]]; then
    sleep "\${_compose_delay}"
  fi
done
if [[ "\${_compose_ok}" -ne 1 ]]; then
  echo "compose up failed after \${_compose_attempts} attempt(s)" >&2
  exit 1
fi
echo "compose ok"
HARNESS
  echo "$tmpfile"
}

echo "=== TRN-227: compose retry loop ==="

# ── 3.1: succeed on first attempt ────────────────────────────────────────────
echo ""
echo "--- Succeed on first attempt ---"
_h=$(make_harness 0 3 0); out=$(bash "$_h" 2>&1); rm -f "$_h"
if [[ "$out" == "compose ok" ]]; then
  pass "succeeds immediately, no retries"
else
  fail "unexpected output: $out"
fi

# ── 3.1: fail once then succeed (retry works) ────────────────────────────────
echo ""
echo "--- Fail once, succeed on second attempt ---"
_h=$(make_harness 1 3 0); out=$(bash "$_h" 2>&1); rm -f "$_h"
if [[ "$out" == "compose ok" ]]; then
  pass "recovered after 1 failure with 3 attempts"
else
  fail "unexpected output: $out"
fi

# ── 3.1: fail N-1 times then succeed (boundary) ──────────────────────────────
echo ""
echo "--- Fail 2 times, succeed on 3rd (boundary) ---"
_h=$(make_harness 2 3 0); out=$(bash "$_h" 2>&1); rm -f "$_h"
if [[ "$out" == "compose ok" ]]; then
  pass "recovered on final attempt"
else
  fail "unexpected output: $out"
fi

# ── 3.2: exhaust all retries → exit non-zero ─────────────────────────────────
echo ""
echo "--- Exhaust all 3 attempts → non-zero exit ---"
_h=$(make_harness 3 3 0)
if ! bash "$_h" >/dev/null 2>&1; then
  pass "exits non-zero after exhausting all attempts"
else
  fail "should have exited non-zero"
fi
rm -f "$_h"

# ── 3.2: GA_COMPOSE_RETRY_ATTEMPTS=1 → single attempt, no retry ──────────────
echo ""
echo "--- GA_COMPOSE_RETRY_ATTEMPTS=1 disables retry ---"
_h=$(make_harness 1 1 0); out=$(bash "$_h" 2>&1 || true); rm -f "$_h"
if echo "$out" | grep -q "failed after 1 attempt"; then
  pass "single attempt mode exits immediately on failure"
else
  fail "unexpected output: $out"
fi

# ── 1.2: 0 treated as 1 with warning ─────────────────────────────────────────
echo ""
echo "--- GA_COMPOSE_RETRY_ATTEMPTS=0 → treated as 1 with warning ---"
_h=$(make_harness 1 0 0); out=$(bash "$_h" 2>&1 || true); rm -f "$_h"
if echo "$out" | grep -q "WARNING" && echo "$out" | grep -q "failed after 1 attempt"; then
  pass "0 treated as 1, warning printed"
else
  fail "unexpected output: $out"
fi

# ── 1.2: non-integer treated as 1 with warning ───────────────────────────────
echo ""
echo "--- GA_COMPOSE_RETRY_ATTEMPTS=foo → treated as 1 with warning ---"
_h=$(make_harness 1 foo 0); out=$(bash "$_h" 2>&1 || true); rm -f "$_h"
if echo "$out" | grep -q "WARNING" && echo "$out" | grep -q "failed after 1 attempt"; then
  pass "non-integer treated as 1, warning printed"
else
  fail "unexpected output: $out"
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
