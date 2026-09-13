#!/usr/bin/env bash
# TRN-97: integration test for the GA_LIGHTHOUSE_ENABLED install.sh flag.
#
# install.sh has no dry-run mode and its compose/Caddy generation is embedded
# mid-script behind podman/machine prerequisites, so — following the pattern of
# tests/integration/test_install_config.sh — this test reproduces the exact
# guarded generation blocks from install.sh in isolation and asserts on their
# output. The reproduced heredocs are kept byte-identical to install.sh; any
# divergence is a review signal.
#
# It verifies:
#   1. GA_LIGHTHOUSE_ENABLED=true → compose.yml contains the ga-lighthouse
#      service with ONLY ga-portside in its networks.
#   2. GA_LIGHTHOUSE_ENABLED=true → initial-config.json contains a
#      "ga-lighthouse" Caddy route.
#   3. The generated initial-config.json is valid JSON.
#   4. GA_LIGHTHOUSE_ENABLED=false (default) → neither file contains any
#      lighthouse block.
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INSTALL="$REPO_DIR/scripts/install.sh"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0
FAIL=0
pass() { PASS=$((PASS+1)); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

# ── Guard: the real install.sh must still carry the lighthouse blocks ─────────
# Cheap drift detector — if these anchors disappear from install.sh, the
# reproduced blocks below are stale.
grep -q 'localhost/lighthouse:latest' "$INSTALL" && pass "install.sh builds the lighthouse image" || fail "install.sh missing lighthouse image build"
grep -q '"@id": "ga-lighthouse"' "$INSTALL" && pass "install.sh emits the ga-lighthouse Caddy route" || fail "install.sh missing ga-lighthouse Caddy route"
grep -q 'container_name: ga-lighthouse' "$INSTALL" && pass "install.sh emits the ga-lighthouse compose service" || fail "install.sh missing ga-lighthouse compose service"

# ── Reproduce install.sh's compose ga-lighthouse block ────────────────────────
gen_compose_tail() {
  local GA_LIGHTHOUSE_ENABLED="$1"
  local GA_API_KEY="$2"
  cat <<COMPOSE_EOF
    command: ["caddy", "run", "--config", "/config/initial-config.json", "--resume"]
$(if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
  printf '  ga-lighthouse:\n'
  printf '    image: localhost/lighthouse:latest\n'
  printf '    container_name: ga-lighthouse\n'
  printf '    restart: always\n'
  printf '    networks:\n'
  printf '      - ga-portside\n'
  printf '    environment:\n'
  printf '      TRANSPORT_URL: "http://ga-transport:64057"\n'
  printf '      GA_LIGHTHOUSE_PORT: "7474"\n'
  printf '    secrets:\n'
  printf '      - ga-transport-secret\n'
  if [[ -n "${GA_API_KEY:-}" ]]; then
    printf '      - ga-api-key\n'
  fi
  printf '    healthcheck:\n'
  printf '      test: ["CMD", "curl", "-f", "http://localhost:7474/healthz"]\n'
  printf '      interval: 30s\n'
  printf '      retries: 3\n'
fi)
networks:
  ga-portside:
    external: true
COMPOSE_EOF
}

# ── Reproduce install.sh's Caddy _LIGHTHOUSE_ROUTE + interpolation ────────────
gen_caddy() {
  local GA_LIGHTHOUSE_ENABLED="$1"
  local GA_API_KEY="$2"
  local _AUTH_ROUTES='            {"@id": "ga-transport-mcp", "match": [{"path": ["/mcp*"]}], "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]},'
  local _LIGHTHOUSE_ROUTE
  if [[ "${GA_LIGHTHOUSE_ENABLED:-false}" == "true" ]]; then
    if [[ -n "${GA_API_KEY:-}" ]]; then
      _LIGHTHOUSE_ROUTE=$(cat <<LHEOF
            {
              "@id": "ga-lighthouse",
              "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
              "handle": [
                {
                  "handler": "reverse_proxy",
                  "upstreams": [{"dial": "ga-transport:64057"}],
                  "rewrite": {"method": "GET", "uri": "/dashboard/auth"},
                  "headers": {"request": {"set": {
                    "X-Forwarded-Method": ["{http.request.method}"],
                    "X-Forwarded-Uri": ["{http.request.uri}"],
                    "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]
                  }}},
                  "handle_response": [{"match": {"status_code": [2]}, "routes": [{"handle": [{"handler": "vars"}]}]}]
                },
                {"handler": "rewrite", "uri_substring": [{"find": "/lighthouse", "replace": ""}]},
                {"handler": "reverse_proxy", "upstreams": [{"dial": "ga-lighthouse:7474"}],
                 "headers": {"request": {"set": {"X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]}}}}
              ]
            },
LHEOF
)
    else
      _LIGHTHOUSE_ROUTE=$(cat <<LHEOF
            {
              "@id": "ga-lighthouse",
              "match": [{"path": ["/lighthouse", "/lighthouse/*"]}],
              "handle": [
                {"handler": "rewrite", "uri_substring": [{"find": "/lighthouse", "replace": ""}]},
                {"handler": "reverse_proxy", "upstreams": [{"dial": "ga-lighthouse:7474"}]}
              ]
            },
LHEOF
)
    fi
  else
    _LIGHTHOUSE_ROUTE=""
  fi
  cat <<CADDY_EOF
{
  "admin": {"listen": "0.0.0.0:2019"},
  "apps": {
    "http": {
      "servers": {
        "ga-main": {
          "listen": [":64057"],
          "automatic_https": {"disable": true},
          "routes": [
${_AUTH_ROUTES}
${_LIGHTHOUSE_ROUTE}
            {
              "@id": "ga-transport-misc",
              "match": [{"path": ["/health"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}]}]
            }
          ]
        }
      }
    },
    "tls": {}
  }
}
CADDY_EOF
}

# ── Case A: enabled ──────────────────────────────────────────────────────────
echo ""
echo "--- Case A: GA_LIGHTHOUSE_ENABLED=true ---"
gen_compose_tail true "" > "$TMPDIR/compose_on.yml"
gen_caddy true "" > "$TMPDIR/caddy_on.json"

grep -q 'container_name: ga-lighthouse' "$TMPDIR/compose_on.yml" \
  && pass "compose contains ga-lighthouse service" || fail "compose missing ga-lighthouse service"

# ga-portside present, ga-starboard absent within the lighthouse block.
_LH_BLOCK="$(awk '/ga-lighthouse:/{f=1} f{print} /^networks:/{f=0}' "$TMPDIR/compose_on.yml")"
echo "$_LH_BLOCK" | grep -q 'ga-portside' \
  && pass "ga-lighthouse attached to ga-portside" || fail "ga-lighthouse missing ga-portside"
if echo "$_LH_BLOCK" | grep -q 'ga-starboard'; then
  fail "ga-lighthouse MUST NOT list ga-starboard"
else
  pass "ga-lighthouse has no ga-starboard network"
fi

grep -q '"ga-lighthouse"' "$TMPDIR/caddy_on.json" \
  && pass "Caddy config contains ga-lighthouse route" || fail "Caddy config missing ga-lighthouse route"

if python3 -m json.tool "$TMPDIR/caddy_on.json" >/dev/null 2>&1; then
  pass "Caddy initial-config.json is valid JSON (enabled)"
else
  fail "Caddy initial-config.json is NOT valid JSON (enabled)"
fi

# ── Case A2: enabled + API key (forward_auth route) ──────────────────────────
echo ""
echo "--- Case A2: GA_LIGHTHOUSE_ENABLED=true + GA_API_KEY set ---"
gen_caddy true "some-key" > "$TMPDIR/caddy_on_keyed.json"
grep -q '"ga-lighthouse"' "$TMPDIR/caddy_on_keyed.json" \
  && pass "Caddy route present with API key" || fail "Caddy route missing with API key"
grep -q '/dashboard/auth' "$TMPDIR/caddy_on_keyed.json" \
  && pass "keyed route gates via /dashboard/auth" || fail "keyed route missing forward-auth gate"
if python3 -m json.tool "$TMPDIR/caddy_on_keyed.json" >/dev/null 2>&1; then
  pass "Caddy initial-config.json is valid JSON (enabled+keyed)"
else
  fail "Caddy initial-config.json is NOT valid JSON (enabled+keyed)"
fi

# ── Case B: disabled (default) ───────────────────────────────────────────────
echo ""
echo "--- Case B: GA_LIGHTHOUSE_ENABLED=false (default) ---"
gen_compose_tail false "" > "$TMPDIR/compose_off.yml"
gen_caddy false "" > "$TMPDIR/caddy_off.json"

if grep -q 'ga-lighthouse' "$TMPDIR/compose_off.yml"; then
  fail "compose MUST NOT contain lighthouse when disabled"
else
  pass "compose has no lighthouse block when disabled"
fi
if grep -q 'ga-lighthouse' "$TMPDIR/caddy_off.json"; then
  fail "Caddy config MUST NOT contain lighthouse route when disabled"
else
  pass "Caddy config has no lighthouse route when disabled"
fi
if python3 -m json.tool "$TMPDIR/caddy_off.json" >/dev/null 2>&1; then
  pass "Caddy initial-config.json is valid JSON (disabled)"
else
  fail "Caddy initial-config.json is NOT valid JSON (disabled)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
