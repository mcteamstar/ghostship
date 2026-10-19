#!/usr/bin/env bash
# Integration test: bin/install.sh auto-migration ghostship.conf → .yaml.
#
# TRN-253 — when install.sh finds config/ghostship.conf with no
# config/ghostship.yaml, it migrates the conf to YAML (via
# bin/lib/yaml_config.py), writes config/ghostship.yaml holding only the
# non-default values, renames the old file to config/ghostship.conf.bak, and
# proceeds with the install.
#
# Approach: the migration and config-resolution steps run BEFORE install.sh's
# --client-only early-exit, so we stage a minimal ghostship tree in a sandbox
# (the real install.sh + yaml_config.py + a config/ dir + a stub `ghostship`
# binary so the client-only `ghostship setup` call exits 0) and run it with
# --client-only. GHOSTSHIP_DIR then resolves to the sandbox tree, so migration
# operates on the sandbox config/ and never touches the real repo.
#
# Run: bash tests/integration/test_install_migration.sh
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
URL="http://localhost:64057/mcp"

# shellcheck source=helpers/sandbox.sh
source "$SCRIPT_DIR/helpers/sandbox.sh"

# Stage a minimal ghostship tree inside the current sandbox and echo its path.
# Copies the real install.sh + yaml_config.py, creates config/ with a legacy
# conf, and drops a stub `ghostship` CLI so the --client-only path exits 0.
stage_ghostship_tree() {
  local conf_body="$1"
  local tree="${SANDBOX_DIR}/ghostship"
  mkdir -p "${tree}/bin/lib" "${tree}/config"
  cp "${REPO_DIR}/bin/install.sh"       "${tree}/bin/install.sh"
  cp "${REPO_DIR}/bin/lib/yaml_config.py" "${tree}/bin/lib/yaml_config.py"
  cp "${REPO_DIR}/bin/lib/agent_backends.sh" "${tree}/bin/lib/agent_backends.sh"
  cp "${REPO_DIR}/bin/lib/portal_host.sh" "${tree}/bin/lib/portal_host.sh"
  cp -r "${REPO_DIR}/bin/lib/vendor" "${tree}/bin/lib/vendor"
  chmod +x "${tree}/bin/install.sh"
  printf '%s' "$conf_body" > "${tree}/config/ghostship.conf"
  # Stub ghostship CLI — the client-only path calls "$GHOSTSHIP_DIR/ghostship setup".
  cat > "${tree}/ghostship" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
  chmod +x "${tree}/ghostship"
  echo "$tree"
}

echo "=== Test: install.sh auto-migration ghostship.conf → ghostship.yaml ==="

# ── Test 1: migration runs, writes yaml, renames conf, install proceeds ───────
echo ""
echo "--- Test 1: conf present, no yaml → migration happens ---"
sandbox_setup
TREE="$(stage_ghostship_tree 'PORT=9000
GA_MAX_ACTIVE_CREWS=6
KIRO_IDENTITY_PROVIDER="https://idp.example.com"
')"
sandbox_run_script "${TREE}/bin/install.sh" --client-only --url "$URL"

if [[ "$SANDBOX_STATUS" -eq 0 ]]; then
  pass "install completed (exit 0) after migration"
else
  fail "install did not complete after migration (status=${SANDBOX_STATUS})"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

if [[ -f "${TREE}/config/ghostship.yaml" ]]; then
  pass "config/ghostship.yaml created"
else
  fail "config/ghostship.yaml was not created"
fi

if [[ -f "${TREE}/config/ghostship.conf.bak" && ! -f "${TREE}/config/ghostship.conf" ]]; then
  pass "ghostship.conf renamed to ghostship.conf.bak"
else
  fail "ghostship.conf was not renamed to .bak"
fi

if sandbox_output_contains "migrated to config/ghostship.yaml" || \
   sandbox_output_contains "Config migrated"; then
  pass "migration notice printed"
else
  fail "migration notice not printed"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# The migrated YAML carries the non-default values under their YAML paths.
if [[ -f "${TREE}/config/ghostship.yaml" ]] && \
   grep -q 'port: 9000' "${TREE}/config/ghostship.yaml" && \
   grep -q 'max_active: 6' "${TREE}/config/ghostship.yaml" && \
   grep -q 'identity_center:' "${TREE}/config/ghostship.yaml"; then
  pass "migrated yaml holds the non-default values under YAML paths"
else
  fail "migrated yaml missing expected values"
  [[ -f "${TREE}/config/ghostship.yaml" ]] && echo "    yaml: $(cat "${TREE}/config/ghostship.yaml")"
fi

# ── Test 2: no migration when yaml already exists ─────────────────────────────
echo ""
echo "--- Test 2: both conf and yaml present → conf left untouched ---"
sandbox_setup
TREE="$(stage_ghostship_tree 'PORT=1234
')"
# Pre-create a yaml so migration must NOT fire.
printf 'network:\n  port: 7777\n' > "${TREE}/config/ghostship.yaml"
sandbox_run_script "${TREE}/bin/install.sh" --client-only --url "$URL"

if [[ -f "${TREE}/config/ghostship.conf" && ! -f "${TREE}/config/ghostship.conf.bak" ]]; then
  pass "existing conf left untouched when yaml already present"
else
  fail "conf was migrated despite an existing yaml"
  echo "    output: ${SANDBOX_OUTPUT}"
fi

# ── Test 3: unknown conf keys surface a warning ───────────────────────────────
echo ""
echo "--- Test 3: unknown conf key warned during migration ---"
sandbox_setup
TREE="$(stage_ghostship_tree 'SOME_LEGACY_KEY=value123
')"
sandbox_run_script "${TREE}/bin/install.sh" --client-only --url "$URL"
if sandbox_output_contains "SOME_LEGACY_KEY"; then
  pass "unknown conf key reported during migration"
else
  fail "unknown conf key not reported"
  echo "    output: ${SANDBOX_OUTPUT}"
fi
if [[ -f "${TREE}/config/ghostship.yaml" ]] && \
   grep -q 'UNKNOWN: SOME_LEGACY_KEY' "${TREE}/config/ghostship.yaml"; then
  pass "unknown key preserved as a # UNKNOWN comment in yaml"
else
  fail "unknown key not preserved as a comment"
fi

sandbox_report
