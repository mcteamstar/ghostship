#!/usr/bin/env bash
# Test cases for install.sh's stale-build-cache detection (install.sh:485-509).
# Some build backends (observed with podman) don't reliably invalidate a
# cached layer when only a --build-arg VERSION value changes, so install.sh
# compares each image's currently-baked version against VERSION and forces
# --no-cache only when they differ. Reproduces that logic in isolation with a
# stub podman, mirroring the pattern in test_install_config.sh -- no real
# podman or images required.
set -eo pipefail

PASS=0
FAIL=0

pass() { ((PASS++)); echo "  ✓ $1"; }
fail() { ((FAIL++)); echo "  ✗ $1"; }

test_cache_detection() {
  local VERSION="$1"
  local STUB_IMAGE_EXISTS="$2"       # "true" or "false"
  local STUB_TRANSPORT_VERSION="$3"
  local STUB_CREW_VERSION="$4"

  _stub_podman() {
    case "$1" in
      image)
        [[ "$STUB_IMAGE_EXISTS" == "true" ]] && return 0 || return 1
        ;;
      run)
        echo "$STUB_TRANSPORT_VERSION"
        ;;
      inspect)
        echo "$STUB_CREW_VERSION"
        ;;
    esac
  }

  local _TRANSPORT_BUILD_FLAGS=()
  if _stub_podman image exists localhost/transport:latest 2>/dev/null; then
    local _baked_transport_version
    _baked_transport_version="$(_stub_podman run --rm localhost/transport:latest sh -c 'echo $TRANSPORT_VERSION' 2>/dev/null || true)"
    if [[ "$_baked_transport_version" != "$VERSION" ]]; then
      _TRANSPORT_BUILD_FLAGS=(--no-cache)
    fi
  fi

  local _CREW_BUILD_FLAGS=()
  if _stub_podman image exists localhost/spec-ops:latest 2>/dev/null; then
    local _baked_crew_version
    _baked_crew_version="$(_stub_podman inspect localhost/spec-ops:latest --format '{{ index .Labels "org.ghostship.version" }}' 2>/dev/null || true)"
    if [[ "$_baked_crew_version" != "${VERSION}-spec-ops" ]]; then
      _CREW_BUILD_FLAGS=(--no-cache)
    fi
  fi

  echo "TRANSPORT_FLAGS=${_TRANSPORT_BUILD_FLAGS[*]:-}"
  echo "CREW_FLAGS=${_CREW_BUILD_FLAGS[*]:-}"
}

echo "=== Test: install.sh stale-build-cache detection ==="

echo ""
echo "--- Test 1: No existing images -> no cache flags (fresh install) ---"
OUTPUT=$(test_cache_detection "0.2.2" "false" "" "")
echo "$OUTPUT" | grep -q "^TRANSPORT_FLAGS=$" && pass "No transport image -> no --no-cache" || fail "Unexpected transport flags (got: $(echo "$OUTPUT" | grep TRANSPORT_FLAGS))"
echo "$OUTPUT" | grep -q "^CREW_FLAGS=$" && pass "No crew image -> no --no-cache" || fail "Unexpected crew flags (got: $(echo "$OUTPUT" | grep CREW_FLAGS))"

echo ""
echo "--- Test 2: Baked version matches VERSION -> no cache flags (ordinary reinstall) ---"
OUTPUT=$(test_cache_detection "0.2.2" "true" "0.2.2" "0.2.2-spec-ops")
echo "$OUTPUT" | grep -q "^TRANSPORT_FLAGS=$" && pass "Matching transport version -> no --no-cache" || fail "Unexpected transport flags (got: $(echo "$OUTPUT" | grep TRANSPORT_FLAGS))"
echo "$OUTPUT" | grep -q "^CREW_FLAGS=$" && pass "Matching crew version -> no --no-cache" || fail "Unexpected crew flags (got: $(echo "$OUTPUT" | grep CREW_FLAGS))"

echo ""
echo "--- Test 3: Baked transport version differs -> forces --no-cache ---"
OUTPUT=$(test_cache_detection "0.2.2" "true" "0.2.1" "0.2.2-spec-ops")
echo "$OUTPUT" | grep -q "^TRANSPORT_FLAGS=--no-cache$" && pass "Stale transport version -> --no-cache" || fail "Stale transport version did not force --no-cache (got: $(echo "$OUTPUT" | grep TRANSPORT_FLAGS))"
echo "$OUTPUT" | grep -q "^CREW_FLAGS=$" && pass "Crew version still matches -> no --no-cache" || fail "Unexpected crew flags (got: $(echo "$OUTPUT" | grep CREW_FLAGS))"

echo ""
echo "--- Test 4: Baked crew version differs -> forces --no-cache ---"
OUTPUT=$(test_cache_detection "0.2.2" "true" "0.2.2" "0.2.1-spec-ops")
echo "$OUTPUT" | grep -q "^TRANSPORT_FLAGS=$" && pass "Transport version still matches -> no --no-cache" || fail "Unexpected transport flags (got: $(echo "$OUTPUT" | grep TRANSPORT_FLAGS))"
echo "$OUTPUT" | grep -q "^CREW_FLAGS=--no-cache$" && pass "Stale crew version -> --no-cache" || fail "Stale crew version did not force --no-cache (got: $(echo "$OUTPUT" | grep CREW_FLAGS))"

echo ""
echo "--- Test 5: Both baked versions stale -> both forced --no-cache ---"
OUTPUT=$(test_cache_detection "0.2.2" "true" "0.2.0" "0.2.0-spec-ops")
echo "$OUTPUT" | grep -q "^TRANSPORT_FLAGS=--no-cache$" && pass "Stale transport version -> --no-cache" || fail "Unexpected transport flags (got: $(echo "$OUTPUT" | grep TRANSPORT_FLAGS))"
echo "$OUTPUT" | grep -q "^CREW_FLAGS=--no-cache$" && pass "Stale crew version -> --no-cache" || fail "Unexpected crew flags (got: $(echo "$OUTPUT" | grep CREW_FLAGS))"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
