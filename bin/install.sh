#!/usr/bin/env bash
# Install/update Ghost Academy locally on macOS or Linux.
#
# Builds the crew + transport images and starts the transport and Caddy
# (ga-portal) with podman-compose from a generated compose.yml. Caddy is
# published on HOST:PORT (default 127.0.0.1, loopback only); a non-loopback HOST
# needs an API key or network.api_key: false. On macOS, Podman runs inside a
# lightweight Linux VM ("podman machine"); on Linux it runs directly on
# the host kernel, no VM involved.
#
# Run:
#   ./install.sh [--config <path>] [--identity-provider <url>] \
#                [--region <region>] [--port <port>] \
#                [--model <model>] [--api-key <key>]
#
# Config file: copy config/ghostship.yaml.example to config/ghostship.yaml and
# edit the keys you want to override, OR pass an explicit file:
#   ./install.sh --config my-config.yaml
# to persist settings across reinstalls. Config is YAML, resolved by a
# three-layer deep merge (built-in defaults → repo → XDG). See
# docs/configuration.md.
#
# After a fresh install, register the MCP server and call launch:
#   kiro-cli mcp add --name ghostship --url http://localhost:64057/mcp --scope global
#   (from Kiro CLI) ghostship__launch(crew_id="general")
#
# Identity provider config: kiro-cli login needs to know which identity
# provider/region to authenticate against — without it, it falls back to
# Builder ID (free tier), which is likely not what an org-licensed kiro-cli
# install should use. Resolved in this order:
#   1. --config <path>   — a YAML file setting backends.kiro.identity_center.url
#                           and backends.kiro.identity_center.region
#   2. --identity-provider / --region flags
#   3. Interactive prompt, if running in a terminal and still unset
#
# Port: MCP and file transfer both listen on --port (default 64057) — one port
# serves all routes, matching server.py's unified app.
#
# Host: HOST (network.host) is the address ga-portal publishes on — default
# 127.0.0.1. The transport always listens on 0.0.0.0 inside its container.
#
# API key: network.api_key in the YAML, or --api-key <key>, enables MCP
# bearer-token auth. The flag wins and is persisted to your data directory, so
# it stays enabled on future installs without repeating it; --api-key ""
# (empty) clears the saved flag key. network.api_key: false is the explicit
# opt-out for a non-loopback HOST. See docs/auth.md.
# set -e: exit on any command failure. set -o pipefail: exit on failures
# within pipelines. Together these ensure that podman machine ssh failures
# (including those in command-substitution subshells like GUEST_UID=...)
# propagate as non-zero exits. Explicit error guards below add diagnostic
# messages to name *what* failed.
set -eo pipefail

GHOSTSHIP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OS="$(uname -s)"

# ── Interactive setup helpers (TRN-233) ──────────────────────────────────────
# _prompt reads one value with a default. `printf -v` writes into the named
# variable without eval. The `|| true` keeps a read failure (EOF when stdin is
# not a tty, e.g. `--wizard </dev/null` or a piped install) from aborting the
# script under `set -e`; the value falls back to the default in that case.
_prompt() {
    local prompt="$1" default="$2" var_name="$3"
    local value
    read -r -p "${prompt} [${default}]: " value || true
    value="${value:-$default}"
    printf -v "$var_name" '%s' "$value"
}

# _interactive_setup walks the operator through backend selection and non-secret
# config, then writes config/ghostship.yaml. Secrets are never collected here —
# are deferred to `ghostship auth login <backend>` after install.
_interactive_setup() {
    echo "=== Ghostship Interactive Setup ==="

    # 1. Default backend — validate against known values, re-prompt on unknown.
    while true; do
        _prompt "Default agent backend (kiro/claude/codex)" "kiro" GA_CREW_AGENT
        case "$GA_CREW_AGENT" in
            kiro|claude|codex) break ;;
            *) echo "  Unknown backend '${GA_CREW_AGENT}'. Choose one of: kiro, claude, codex." ;;
        esac
    done

    # 2. Additional backends — comma-separated, validate each.
    while true; do
        _prompt "Additional backends to enable, comma-separated (blank = none)" "" _extra_backends
        if [[ -z "$_extra_backends" ]]; then
            break
        fi
        local _ok=true _b
        local _IFS_SAVE="$IFS"
        IFS=',' read -r -a _extra_arr <<< "$_extra_backends"
        IFS="$_IFS_SAVE"
        for _b in "${_extra_arr[@]}"; do
            _b="${_b// /}"
            case "$_b" in
                kiro|claude|codex) ;;
                *) echo "  Unknown backend '${_b}'. Choose from: kiro, claude, codex."; _ok=false ;;
            esac
        done
        if [[ "$_ok" == "true" ]]; then
            GA_CREW_AGENT="${GA_CREW_AGENT},${_extra_backends}"
            break
        fi
    done

    # 3. Non-secret config per selected backend.
    if [[ "$GA_CREW_AGENT" == *kiro* ]]; then
        _prompt "kiro-cli identity provider URL (blank = Builder ID)" "" KIRO_IDENTITY_PROVIDER
        if [[ -n "${KIRO_IDENTITY_PROVIDER:-}" ]]; then
            _prompt "AWS region for that identity provider" "" KIRO_REGION
        fi
    fi
    if [[ "$GA_CREW_AGENT" == *claude* ]]; then
        echo "  Claude: no config needed here — you'll be offered a login after the transport starts."
    fi
    if [[ "$GA_CREW_AGENT" == *codex* ]]; then
        _prompt "OpenAI-compatible base URL (blank = https://api.openai.com/v1; can point at a local proxy like litellm)" "" OPENAI_BASE_URL
        echo "  Codex: you'll be offered a login after the transport starts."
    fi

    # 4. Write config/ghostship.yaml from an internal template (TRN-253).
    # Operator-supplied values are written uncommented; every other key is
    # shown commented-out at its default. Secrets are never written here.
    mkdir -p "${GHOSTSHIP_DIR}/config"
    local _yaml="${GHOSTSHIP_DIR}/config/ghostship.yaml"

    # Prompt before overwriting an existing config (preserve operator intent).
    if [[ -f "$_yaml" ]]; then
        local _overwrite="n"
        _prompt "config/ghostship.yaml already exists — overwrite? (y/N)" "n" _overwrite
        if [[ "${_overwrite,,}" != "y" ]]; then
            echo "✓ Keeping existing config/ghostship.yaml (wizard values discarded)."
            return 0
        fi
    fi

    # Comment helper: emit "key: value" uncommented when set, else commented.
    _emit() {  # _emit <indent> <key> <value> <default>
        local indent="$1" key="$2" value="$3" default="$4"
        if [[ -n "$value" ]]; then
            printf '%s%s: "%s"\n' "$indent" "$key" "$value"
        else
            printf '%s# %s: "%s"\n' "$indent" "$key" "$default"
        fi
    }

    {
        echo "# Generated by ./install.sh --wizard on $(date)"
        echo "# Every unset key below is commented out at its built-in default."
        echo "# Full reference: config/ghostship.yaml.example and docs/configuration.md"
        echo ""
        echo "backends:"
        printf '  agent: "%s"\n' "${GA_CREW_AGENT}"
        echo "  kiro:"
        _emit "    " "identity_provider" "${KIRO_IDENTITY_PROVIDER:-}" ""
        _emit "    " "region" "${KIRO_REGION:-}" ""
        echo "  codex:"
        _emit "    " "base_url" "${OPENAI_BASE_URL:-}" ""
    } > "${_yaml}"
    unset -f _emit
    chmod 600 "${_yaml}"
    echo "✓ Config written to ${_yaml}"
}

# ── Built-in defaults (literal assignments, BEFORE config sourcing) ──────────
# Resolution order: built-in default → config file → CLI flag.
# A literal assignment here ensures an ambient env var from the invoking shell
# is unconditionally overwritten — only the config file or a flag can override.
PORT=64057
KIRO_IDENTITY_PROVIDER=""
KIRO_REGION=""
KC_MODEL_KIRO_OVERRIDE=""
KC_MODEL_KIRO_DEFAULT=""
KC_MODEL_CLAUDE_OVERRIDE=""
KC_MODEL_CLAUDE_DEFAULT=""
KC_MODEL_CODEX_OVERRIDE=""
KC_MODEL_CODEX_DEFAULT=""
KC_MODEL_DEFAULT=""
GA_HOST_URL=""
GA_API_KEY=""
GA_API_KEY_DISABLED=""        # "true" = network.api_key: false (explicit opt-out)
GA_API_KEY_SOURCE=""          # "yaml" when network.api_key set the key or opt-out
GA_API_KEY_DEPRECATED_OFF=""  # deprecated network.require_api_key: off
GA_DEDICATED_MACHINE=true
GA_MACHINE_CPUS=8
GA_MACHINE_MEMORY=16384
GA_MACHINE_DISK=100
GA_MACHINE_NAME=ghost-academy
GA_MAX_CREWS=20
GA_MAX_ACTIVE_CREWS=3
GA_IDLE_TIMEOUT_SECS=300
GA_SUBAGENT_TIMEOUT_SECS=3600
GA_BATCH_MAX_TASKS=20
GA_PICKUP_MAX_POLL_SECS=30
GA_CREW_AGENT=kiro
# Optional agent backends to enable, comma-separated (claude, codex). Kiro is
# always enabled. Drives the image toolchains and the transport (TRN-202).
GA_AGENT_BACKENDS=""
GA_CREW_ACP_BACKEND=kiro
# Crew model backend keys and the headless kiro key. Config-file vars (set in
# ghostship.conf), not flags — passing a key on the command line would leak it
# into the process list and shell history. install.sh delivers each as a Podman
# secret (ga-crew-*-api-key / ga-kiro-api-key) rather than a plaintext compose
# env var (secret-delivery-hardening). These use the standard names the Claude
# and Codex CLIs read (TRN-226); resetting them here is what stops a key
# exported in the operator's own shell from being picked up.
ANTHROPIC_API_KEY=""
OPENAI_API_KEY=""
KIRO_API_KEY=""
# Long-lived Claude token from `claude setup-token`, injected into Claude-backend
# crews as CLAUDE_CODE_OAUTH_TOKEN (TRN-226). Reset here so a token exported in
# the operator's own shell is never picked up; only ghostship.conf sets it.
CLAUDE_CODE_OAUTH_TOKEN=""
ANTHROPIC_BASE_URL=""
OPENAI_BASE_URL=""
# Deprecated pre-TRN-226 names, still accepted from ghostship.conf (mapped below).
GA_CREW_ANTHROPIC_API_KEY=""
GA_CREW_ANTHROPIC_BASE_URL=""
GA_CREW_OPENAI_API_KEY=""
GA_CREW_OPENAI_BASE_URL=""
GA_MIN_FREE_MEM_GB=2.0
GA_SPAWN_MIN_MEMORY_GB=1.5
GA_RESOURCE_PRESSURE_GB=2.0
GA_RESOURCE_CRITICAL_GB=1.0
GA_SPAWN_PRESSURE_ESCALATE_CYCLES=3
GA_GIT_AUTHOR_NAME=""
GA_GIT_AUTHOR_EMAIL=""
GA_DASHBOARD_PORT_RANGE_START=64058
GA_DASHBOARD_DEFAULT=false  # Set true to allocate a dashboard on every launch
GA_DASHBOARD_PORT_RANGE_SIZE=64
HOST=127.0.0.1  # ga-portal's published address — loopback only by default
GA_ORDERS_DIR=""
GA_TLS_CERTFILE=""
GA_TLS_KEYFILE=""
KC_BASE_IMAGE=""
# Pin for mcteamstar/.agents baked into the crew image (TRN-264). Empty = use
# the Containerfile default ("main"). Set to a tag or SHA for reproducible
# builds; a changed value forces a crew image rebuild. Override via
# machine.images.agents_ref in ghostship.yaml.
AGENTS_REF=""
GA_PORTAL_SESSION_TTL_SECS=86400
GA_RATE_LIMIT_ENABLED=true
GA_RATE_LIMIT_LOGIN_GET=30:60
GA_RATE_LIMIT_LOGIN_POST=5:300
GA_RATE_LIMIT_MCP=300:60
GA_RATE_LIMIT_FILES=60:60
GA_RATE_LIMIT_CREW_API=120:60
GA_RATE_LIMIT_DASHBOARD_AUTH=600:60
KC_IMAGE=localhost/spec-ops:latest
_COMPOSE_RETRY_ATTEMPTS=3     # retries on transient compose up failure (hardcoded)
_COMPOSE_RETRY_DELAY_SECS=2   # sleep between retries in seconds (hardcoded)
# ── Client-only install ──────────────────────────────────────────────────────
# --client-only wires the ghostship CLI + agent harnesses to a (usually remote)
# transport WITHOUT running any container-infrastructure steps. --url selects
# which transport the client connects to (default matches the full-install
# port); --api-key sets the MCP bearer token. Flag-only — not config-file vars.
CLIENT_ONLY=false
CLIENT_ONLY_URL="http://localhost:64057/mcp"
CLIENT_ONLY_API_KEY=""
# ── Caddy reverse proxy ───────────────────────────────────────────────────────
# ga-portal (Caddy) is always installed; there is no opt-out.
# Caddy listens on PORT (same port as the transport, resolved above).
# Default: plain HTTP on 64057 — zero-config installs work at
# http://localhost:64057/mcp with no TLS setup required.
# To enable TLS: set GA_PORTAL_TLS_MODE=acme + GA_PORTAL_DOMAIN (any port).
GA_PORTAL_TLS_MODE=off
GA_PORTAL_DOMAIN=""
# Exposure check: a non-loopback HOST with no API key aborts the install unless
# network.api_key: false opts out explicitly (for deployments that put their own
# auth layer in front — Tailscale, VPN, reverse proxy). Loopback installs never
# need a key. The deprecated GA_REQUIRE_API_KEY / network.require_api_key is
# mapped by yaml_config.py (only `off` has an effect, as the opt-out).

# ── Config file (YAML): extract --config <path> first (peek at $@) ──────────
# Resolve BEFORE the flag-parsing loop so CLI flags override config-file values.
#
# TRN-253: config is now YAML, resolved by bin/lib/yaml_config.py via a
# three-layer deep merge (built-in defaults → repo config/ghostship.yaml → XDG
# override), or (built-in defaults → --config file) when --config is passed.
# The helper emits shell-quoted KEY=value lines which we eval into the
# environment. The transport still reads these as env vars baked into
# compose.yml — Config.from_env() is unchanged.
CONFIG_FILE=""
_args=("$@")
for ((i=0; i < ${#_args[@]}; i++)); do
  if [[ "${_args[i]}" == "--config" ]]; then
    CONFIG_FILE="${_args[i+1]:-}"
    break
  fi
done

_YAML_CONFIG_HELPER="${GHOSTSHIP_DIR}/bin/lib/yaml_config.py"
_REPO_YAML="${GHOSTSHIP_DIR}/config/ghostship.yaml"
_REPO_CONF="${GHOSTSHIP_DIR}/config/ghostship.conf"

# XDG override path (per OS). macOS keeps all ghost-academy files under
# Application Support; Linux follows XDG_CONFIG_HOME (default ~/.config).
if [[ "$OS" == "Darwin" ]]; then
  _XDG_YAML="${HOME}/Library/Application Support/ghost-academy/ghostship.yaml"
else
  _XDG_YAML="${XDG_CONFIG_HOME:-$HOME/.config}/ghost-academy/ghostship.yaml"
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to parse the YAML config." >&2
  exit 1
fi

# PyYAML is vendored at bin/lib/vendor/yaml — no venv, no pip, no network needed.

# ── Auto-migration: ghostship.conf → ghostship.yaml (TRN-253) ────────────────
# When a legacy conf exists with no yaml alongside it, convert mechanically,
# write the yaml, rename the old file to .bak, and warn on any unmapped keys.
# Only runs for the implicit repo config (not for an explicit --config path).
if [[ -z "$CONFIG_FILE" && -f "$_REPO_CONF" && ! -f "$_REPO_YAML" ]]; then
  echo "⚠ Legacy config/ghostship.conf found — migrating to config/ghostship.yaml" >&2
  _MIGRATE_OUT="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER" migrate --conf "$_REPO_CONF" --out "$_REPO_YAML")" || {
    echo "Error: config migration failed." >&2
    exit 1
  }
  if [[ -n "$_MIGRATE_OUT" ]]; then
    echo "  WARNING: the following ghostship.conf keys were not recognised and were" >&2
    echo "           preserved only as '# UNKNOWN:' comments in ghostship.yaml:" >&2
    while IFS= read -r _unk; do
      [[ -n "$_unk" ]] && echo "             ${_unk#UNKNOWN: }" >&2
    done <<< "$_MIGRATE_OUT"
  fi
  mv "$_REPO_CONF" "${_REPO_CONF}.bak"
  echo "✓ Config migrated to config/ghostship.yaml. Old file kept as config/ghostship.conf.bak." >&2
fi

# ── Resolve the merged config into the environment ───────────────────────────
if [[ -n "$CONFIG_FILE" ]]; then
  if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Error: config file does not exist: $CONFIG_FILE" >&2
    exit 1
  fi
  if [[ ! -r "$CONFIG_FILE" ]]; then
    echo "Error: config file is not readable: $CONFIG_FILE" >&2
    exit 1
  fi
  _RESOLVED="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER" resolve --config "$CONFIG_FILE")" || {
    echo "Error: failed to parse config file: $CONFIG_FILE" >&2
    exit 1
  }
  eval "$_RESOLVED"
  echo "✓ Loaded config file: $CONFIG_FILE"
else
  # Implicit resolution: built-in defaults → repo → XDG. The helper applies all
  # three layers itself; we only mark _FOUND_CONFIG when an operator file exists
  # so interactive setup is skipped on an existing install.
  if [[ -f "$_REPO_YAML" || -f "$_XDG_YAML" ]]; then
    _FOUND_CONFIG=true
  fi
  _RESOLVED="$(PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3 "$_YAML_CONFIG_HELPER" resolve --repo "$_REPO_YAML" --xdg "$_XDG_YAML")" || {
    echo "Error: failed to resolve YAML config." >&2
    exit 1
  }
  eval "$_RESOLVED"
  if [[ "${_FOUND_CONFIG:-}" == "true" ]]; then
    echo "✓ Loaded YAML config (repo${_XDG_YAML:+ + XDG override when present})"
  fi
fi

# ── Flag parsing (runs AFTER config sourcing — flags override config) ────────
API_KEY_FLAG_PASSED=0
_FLAG_API_KEY=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config|--identity-provider|--region|--port|--model|--model-default|\
    --public-url|--api-key|--caddy-domain|--caddy-tls-mode|--url)
      # Without this, `shift 2` fails under set -e and the script exits silently.
      [[ $# -ge 2 ]] || { echo "Error: $1 requires a value" >&2; exit 1; } ;;
  esac
  case "$1" in
    --config) shift 2 ;;  # already consumed above
    --identity-provider) KIRO_IDENTITY_PROVIDER="$2"; shift 2 ;;
    --region) KIRO_REGION="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --model) KC_MODEL_KIRO_OVERRIDE="$2"; shift 2 ;;
    --model-default) KC_MODEL_DEFAULT="$2"; shift 2 ;;
    --public-url) GA_HOST_URL="$2"; shift 2 ;;
    --api-key) _FLAG_API_KEY="$2"; API_KEY_FLAG_PASSED=1; shift 2 ;;
    --caddy-domain) GA_PORTAL_DOMAIN="$2"; shift 2 ;;
    --caddy-tls-mode) GA_PORTAL_TLS_MODE="$2"; shift 2 ;;
    --client-only) CLIENT_ONLY=true; shift ;;
    --url) CLIENT_ONLY_URL="$2"; shift 2 ;;
    --wizard) _WIZARD_FLAG=true; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

# ── Interactive mode detection (TRN-233) ─────────────────────────────────────
# Enter interactive guided setup when no config was found and we have a tty, or
# whenever --wizard is passed (regardless of an existing config).
_INTERACTIVE_MODE=false
if [[ -z "${_FOUND_CONFIG:-}" && -t 0 ]] || [[ "${_WIZARD_FLAG:-false}" == "true" ]]; then
  _INTERACTIVE_MODE=true
fi

# ── TLS mode ──────────────────────────────────────────────────────────────────
# Fail on an unknown value. The transport falls back to "off" for unknown values
# while the Caddy config below treats them as internal TLS, so a typo would give
# an HTTPS portal and http:// URLs from the transport.
case "${GA_PORTAL_TLS_MODE:-off}" in
  off|internal|tailscale|acme) ;;
  *) echo "✗ GA_PORTAL_TLS_MODE='${GA_PORTAL_TLS_MODE}' is not one of: off, internal, tailscale, acme" >&2; exit 1 ;;
esac

# ── Agent backends (TRN-202) ─────────────────────────────────────────────────
# The retired GA_INCLUDE_*_AGENT flags are a config error in every mode,
# including --client-only. The toolchain and default checks need a build, so
# they run after the client-only exit below.
# shellcheck source=lib/agent_backends.sh
source "$GHOSTSHIP_DIR/bin/lib/agent_backends.sh"
agent_backends_reject_retired || exit 1
# shellcheck source=lib/portal_host.sh
source "$GHOSTSHIP_DIR/bin/lib/portal_host.sh"

# ── Client-only early-exit ────────────────────────────────────────────────────
# When --client-only is set, wire the ghostship CLI + agent harnesses to a
# (usually remote) transport and skip ALL container-infrastructure steps:
# Podman prerequisites, machine/network setup, image builds, compose up.
# --api-key wins over network.api_key, as for a full install.
if [[ "$CLIENT_ONLY" == "true" ]]; then
  CLIENT_ONLY_API_KEY="${_FLAG_API_KEY:-${GA_API_KEY:-}}"

  # Install the ghostship CLI symlink (same logic as the full install path).
  _LOCAL_BIN="${HOME}/.local/bin"
  mkdir -p "${_LOCAL_BIN}"
  ln -sf "${GHOSTSHIP_DIR}/ghostship" "${_LOCAL_BIN}/ghostship"
  echo "✓ ghostship CLI linked to ${_LOCAL_BIN}/ghostship"

  # Wire all detected agent harnesses via ghostship setup. Call the repo-local
  # binary directly (not through PATH) so this works before ~/.local/bin is on
  # PATH. Forward --api-key only when a key was provided.
  "$GHOSTSHIP_DIR/ghostship" setup --url "$CLIENT_ONLY_URL" ${CLIENT_ONLY_API_KEY:+--api-key "$CLIENT_ONLY_API_KEY"}

  # PATH warning (same one-liner as the full install path).
  if [[ ":${PATH}:" != *":${_LOCAL_BIN}:"* ]]; then
    echo "  Add ~/.local/bin to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
  fi

  exit 0
fi

# ── Model backend base-URL alias mapping (TRN-226) ───────────────────────────
# ANTHROPIC_BASE_URL / OPENAI_BASE_URL replace the GA_CREW_-prefixed names. The
# old name still works for this run with a warning; when both are set, the new
# name wins. These are non-secret config, so they are still mapped here. The
# credential aliases (GA_CREW_ANTHROPIC_API_KEY / GA_CREW_OPENAI_API_KEY) are
# handled by the ignored-setting warning below.
for _new in ANTHROPIC_BASE_URL OPENAI_BASE_URL; do
  _old="GA_CREW_${_new}"
  if [[ -n "${!_old:-}" ]]; then
    echo "  WARNING: ${_old} is deprecated — rename it to ${_new} in ghostship.conf." >&2
    if [[ -z "${!_new:-}" ]]; then
      printf -v "$_new" '%s' "${!_old}"
    else
      echo "  ${_new} is also set; ignoring ${_old}." >&2
    fi
  fi
done
unset _new _old

# ── Backend credentials are no longer installer-managed (TRN-233) ─────────────
# The installer has no code path that can create, delete or mount a backend
# credential; they are managed with `ghostship auth login|logout|status` and
# resolved per launch from DATA_DIR/credentials/. If the conf (or the operator's
# shell, though these are reset above) still sets any backend credential — or
# one of the two deprecated credential aliases — warn that it is ignored and
# unset it so it cannot leak into the compose file or a crew environment.
for _ignored in \
  ANTHROPIC_API_KEY \
  CLAUDE_CODE_OAUTH_TOKEN \
  OPENAI_API_KEY \
  KIRO_API_KEY \
  GA_CREW_ANTHROPIC_API_KEY \
  GA_CREW_OPENAI_API_KEY; do
  if [[ -n "${!_ignored:-}" ]]; then
    echo "  WARNING: ${_ignored} is no longer used by the installer and is ignored." >&2
    echo "           Backend credentials are managed with 'ghostship auth login <backend>'." >&2
    unset "$_ignored"
  fi
done
unset _ignored

# ── Agent backend consolidation (TRN-213) ────────────────────────────────────
# GA_CREW_AGENT replaces GA_AGENT_BACKENDS + GA_CREW_ACP_BACKEND.
# Deprecated alias handling: map old vars to GA_CREW_AGENT with a warning.
if [[ -n "${GA_AGENT_BACKENDS:-}" ]]; then
  echo "  WARNING: GA_AGENT_BACKENDS is deprecated — use GA_CREW_AGENT instead." >&2
  echo "  Mapping GA_AGENT_BACKENDS=${GA_AGENT_BACKENDS} → GA_CREW_AGENT for this run." >&2
  if [[ -z "${GA_CREW_AGENT:-}" || "${GA_CREW_AGENT}" == "kiro" ]]; then
    GA_CREW_AGENT="${GA_AGENT_BACKENDS}"
  fi
fi
if [[ -n "${GA_CREW_ACP_BACKEND:-}" && "${GA_CREW_ACP_BACKEND}" != "kiro" ]]; then
  echo "  WARNING: GA_CREW_ACP_BACKEND is deprecated — use GA_CREW_AGENT instead." >&2
  echo "  Mapping GA_CREW_ACP_BACKEND=${GA_CREW_ACP_BACKEND} → GA_CREW_AGENT for this run." >&2
  if [[ -z "${GA_CREW_AGENT:-}" || "${GA_CREW_AGENT}" == "kiro" ]]; then
    GA_CREW_AGENT="${GA_CREW_ACP_BACKEND}"
  fi
fi

# Normalise GA_CREW_AGENT once; the same value drives the image build
# (AGENT_TOOLCHAINS) and the transport environment. Fail before any build on
# an unknown name, so a bad config doesn't cost a full build and a restart loop.
# GA_CREW_AGENT is comma-separated; first entry is the runtime default.
# In interactive mode, _interactive_setup collects backend selection and
# non-secret config (and writes ghostship.conf) first, so the resulting
# GA_CREW_AGENT feeds directly into agent_backends_normalise below.
if [[ "${_INTERACTIVE_MODE:-false}" == "true" ]]; then _interactive_setup; fi
AGENT_TOOLCHAINS="$(agent_backends_normalise "${GA_CREW_AGENT:-kiro}")" || exit 1
agent_backends_validate "$AGENT_TOOLCHAINS" "$GHOSTSHIP_DIR/crews/spec-ops/toolchains" || exit 1
echo "✓ Agent backend: ${GA_CREW_AGENT:-kiro} (runtime default: $(echo "${GA_CREW_AGENT:-kiro}" | cut -d',' -f1))"

if [[ "${_INTERACTIVE_MODE:-false}" != "true" ]]; then
  if [[ -z "${KIRO_IDENTITY_PROVIDER:-}" && -t 0 ]]; then
    read -rp "kiro-cli identity provider URL (blank = default Builder ID login): " KIRO_IDENTITY_PROVIDER
  fi
  if [[ -n "${KIRO_IDENTITY_PROVIDER:-}" && -z "${KIRO_REGION:-}" && -t 0 ]]; then
    read -rp "AWS region for that identity provider: " KIRO_REGION
  fi
fi

# ── Podman ────────────────────────────────────────────────────────────────────

if ! command -v podman >/dev/null 2>&1; then
  echo "✗ podman not found." >&2
  echo "" >&2
  echo "Install podman >= 4.4 before running install.sh:" >&2
  case "$OS" in
    Darwin) echo "  brew install podman" >&2 ;;
    Linux)
      echo "  # Ubuntu/Debian:" >&2
      echo "  sudo apt-get install -y podman podman-compose" >&2
      echo "  # Fedora/RHEL:" >&2
      echo "  sudo dnf install -y podman podman-compose" >&2
      echo "  # Other distros: see docs/manual-install.md" >&2 ;;
  esac
  exit 1
fi

# ── Check prerequisites are installed ────────────────────────────────────────
# podman and podman-compose must be installed before running install.sh.
# See README.md and docs/manual-install.md for install commands.

# ── Verify podman-compose is available ───────────────────────────────────────
# Ghostship's compose.yml uses an external Podman secret (ga-transport-secret).
# docker-compose does NOT support external Podman secrets, so podman-compose is
# the only accepted provider. When both are installed, Podman's provider
# precedence may silently select docker-compose — setting PODMAN_COMPOSE_PROVIDER
# below prevents that.
if ! command -v podman-compose >/dev/null 2>&1; then
  echo "✗ podman-compose not found." >&2
  echo "" >&2
  echo "Ghostship requires podman-compose specifically — docker-compose is not" >&2
  echo "supported because the generated compose.yml uses external Podman secrets." >&2
  echo "" >&2
  echo "Install podman-compose before running install.sh:" >&2
  case "$OS" in
    Darwin) echo "  brew install podman-compose" >&2 ;;
    Linux)
      echo "  # Ubuntu/Debian:" >&2
      echo "  sudo apt-get install -y podman-compose" >&2
      echo "  # Fedora/RHEL:" >&2
      echo "  sudo dnf install -y podman-compose" >&2 ;;
  esac
  exit 1
fi

# ── Podman runtime (machine VM on macOS, native on Linux) ───────────────────

if [[ "$OS" == "Darwin" ]]; then
  # macOS has no container-capable kernel of its own — podman runs inside a
  # Linux VM ("podman machine"). Linux needs none of this; see the else branch.

  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    # ── Dedicated machine provisioning (macOS) ──────────────────────────────
    # A separate podman machine exclusively for Ghost Academy, isolating crew
    # containers from the user's default machine. See design.md.
    _MACHINE="${GA_MACHINE_NAME}"

    if ! podman machine list --format '{{.Name}}' 2>/dev/null | grep -qw "${_MACHINE}"; then
      echo "Initialising dedicated podman machine '${_MACHINE}'..."
      podman machine init "${_MACHINE}" \
        --cpus "${GA_MACHINE_CPUS}" \
        --memory "${GA_MACHINE_MEMORY}" \
        --disk-size "${GA_MACHINE_DISK}"
    fi

    # Start the dedicated machine if not already running
    if ! podman machine inspect "${_MACHINE}" --format '{{.State}}' 2>/dev/null | grep -qi "running"; then
      echo "Starting dedicated podman machine '${_MACHINE}'..."
      podman machine start "${_MACHINE}"
    fi

    # Enable podman-restart.service inside the dedicated machine guest
    podman machine ssh "${_MACHINE}" -- systemctl --user enable podman-restart.service \
      || { echo "Error: failed to enable podman-restart.service in '${_MACHINE}' guest — is the VM running?" >&2; exit 1; }
    echo "✓ podman-restart.service enabled in dedicated machine '${_MACHINE}'"

    # Resolve the in-guest socket path for the dedicated machine
    GUEST_UID="$(podman machine ssh "${_MACHINE}" -- id -u)" \
      || { echo "Error: failed to retrieve guest UID from '${_MACHINE}' — SSH into the VM may be broken" >&2; exit 1; }
    PODMAN_SOCK="/run/user/${GUEST_UID}/podman/podman.sock"
    echo "✓ Dedicated machine '${_MACHINE}' guest socket: ${PODMAN_SOCK}"
  else
    # ── Default machine (macOS, existing behaviour) ──────────────────────────
    if ! podman machine list --format '{{.Name}}' 2>/dev/null | grep -q .; then
      echo "Initialising podman machine..."
      podman machine init --cpus 4 --memory 8192 --disk-size 60
    fi

    if ! podman machine list --format '{{.Running}}' 2>/dev/null | grep -q true; then
      echo "Starting podman machine..."
      podman machine start
    fi

    # podman-restart.service is disabled by default in the guest, so a container
    # run with --restart=always does NOT come back after `podman machine stop` +
    # `start` on its own (verified: it needs this unit enabled). This only
    # affects what happens once you start the machine yourself — it does not
    # make the machine start automatically (no launchd/login autostart is used
    # here on purpose).
    podman machine ssh -- systemctl --user enable podman-restart.service \
      || { echo "Error: failed to enable podman-restart.service in the podman machine guest — is the VM running?" >&2; exit 1; }
    echo "✓ podman-restart.service enabled (transport survives machine restarts)"

    # In-guest socket path (NOT the host-side /var/folders proxy socket from
    # `podman machine inspect` — that path only exists on macOS and can't be
    # bind-mounted into a container, which runs inside the guest VM). Confirmed
    # via `podman machine ssh -- systemctl --user status podman.socket`.
    GUEST_UID="$(podman machine ssh -- id -u)" \
      || { echo "Error: failed to retrieve guest UID via 'podman machine ssh -- id -u' — SSH into the VM may be broken" >&2; exit 1; }
    PODMAN_SOCK="/run/user/${GUEST_UID}/podman/podman.sock"
    echo "✓ Guest podman socket: ${PODMAN_SOCK}"
  fi

  DATA_DIR="$HOME/Library/Application Support/${GA_MACHINE_NAME}/data"

  # The podman-machine guest (Fedora CoreOS) runs SELinux enforcing. The socket
  # is labeled user_tmp_t, which the container's confined domain can't access —
  # bind-mounting it produces a silent "Permission denied" even though the DAC
  # owner/uid mapping (container root -> host uid, verified via
  # `podman exec transport cat /proc/self/uid_map`) lines up correctly. Fixed
  # below with `--security-opt label=disable` on the transport container.
else
  # Linux: podman runs directly on the host, no VM, no guest indirection.

  if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
    # ── Dedicated Podman instance (Linux) ────────────────────────────────────
    # A separate systemd socket-activated Podman service with its own storage
    # root, completely isolated from the default instance.
    _MACHINE="${GA_MACHINE_NAME}"
    _UNIT_DIR="${HOME}/.config/systemd/user"
    _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
    _STORAGE_ROOT="${HOME}/.local/share/${_MACHINE}/containers/storage"

    mkdir -p "${_UNIT_DIR}"

    # Write the dedicated Podman service unit. We run podman system service
    # directly (Type=simple) so it creates the socket file itself — systemd
    # socket activation holds the fd internally without materialising the file,
    # which breaks the socket check on modern kernels (Ubuntu 25.10+).
    # RuntimeDirectory= ensures the socket dir exists under XDG_RUNTIME_DIR.
    cat > "${_UNIT_DIR}/podman-${_MACHINE}.service" <<UNIT_EOF
[Unit]
Description=Ghost Academy dedicated Podman API (${_MACHINE})
After=network.target

[Service]
Type=simple
Environment=CONTAINERS_CONF=${_GA_CONTAINERS_CONF}
RuntimeDirectory=${_MACHINE}
ExecStart=/usr/bin/podman \\
  --root=${_STORAGE_ROOT} \\
  --runroot=${_RUNTIME_DIR}/${_MACHINE}-containers \\
  system service --time=0 unix://${_RUNTIME_DIR}/${_MACHINE}/podman.sock
Restart=on-failure

[Install]
WantedBy=default.target
UNIT_EOF

    echo "✓ Systemd service unit written to ${_UNIT_DIR}"

    # Remove any stale socket-activation unit from a previous install
    rm -f "${_UNIT_DIR}/podman-${_MACHINE}.socket" 2>/dev/null || true

    # Reload and start the service directly (no socket activation)
    systemctl --user daemon-reload
    systemctl --user enable --now "podman-${_MACHINE}.service"

    # Enable lingering for reboot survival
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
    echo "✓ Linger enabled — dedicated instance survives logout/reboot"

    # Set socket path — service creates it under its own RuntimeDirectory
    PODMAN_SOCK="${_RUNTIME_DIR}/${_MACHINE}/podman.sock"

    # Validate the socket file exists. The service creates it on startup so
    # a file-existence check is reliable (unlike socket activation).
    _sock_tries=0
    while [[ ! -S "$PODMAN_SOCK" ]] && (( _sock_tries < 10 )); do
      sleep 1
      (( _sock_tries++ )) || true
    done
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      echo "⚠ Dedicated Podman socket not reachable at: ${PODMAN_SOCK}" >&2
      echo "  Check: systemctl --user status podman-${_MACHINE}.service" >&2
      echo "  Journal: journalctl --user -u podman-${_MACHINE}.service" >&2
      exit 1
    fi
    echo "✓ Dedicated podman socket: ${PODMAN_SOCK}"
  else
    # ── Default Podman instance (Linux, existing behaviour) ──────────────────
    # `podman.socket` gives us the rootless API socket on demand; `enable --now`
    # so it's live immediately, not just on next login.
    systemctl --user enable --now podman.socket 2>/dev/null || true
    systemctl --user enable podman-restart.service 2>/dev/null || true
    echo "✓ podman.socket + podman-restart.service enabled"

    # Enable lingering so systemd user units (and thus the transport container)
    # survive logout. Without this, headless servers tear down the user slice
    # when the last session ends, silently killing the transport.
    loginctl enable-linger "$(whoami)" 2>/dev/null || true
    echo "✓ Linger enabled — transport survives logout/reboot"

    # Socket path: honour an existing PODMAN_SOCK env var (user override) or
    # default to the standard rootless path.
    if [[ -z "${PODMAN_SOCK:-}" ]]; then
      PODMAN_SOCK="/run/user/$(id -u)/podman/podman.sock"
    fi

    # Validate that the socket actually exists (podman.socket activation may
    # need a moment). Bounded retry: up to 5 seconds.
    _sock_tries=0
    while [[ ! -S "$PODMAN_SOCK" ]] && (( _sock_tries < 5 )); do
      sleep 1
      (( _sock_tries++ )) || true
    done
    if [[ ! -S "$PODMAN_SOCK" ]]; then
      echo "⚠ Podman socket not found at: ${PODMAN_SOCK}" >&2
      echo "  Expected path: /run/user/$(id -u)/podman/podman.sock" >&2
      echo "  Check: podman info --format '{{.Host.RemoteSocket.Path}}'" >&2
      echo "  Override: set PODMAN_SOCK=/your/path before running install.sh" >&2
      exit 1
    fi
    echo "✓ podman socket: ${PODMAN_SOCK}"
  fi

  DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/${GA_MACHINE_NAME}/data"

  # SELinux & container labels:
  # `--security-opt label=disable` (applied to the transport container below)
  # disables SELinux label confinement for bind-mounted paths. This is necessary
  # because the podman socket is labeled user_tmp_t, which the container's
  # confined domain cannot access — producing a silent "Permission denied".
  #
  # Trade-off: on SELinux-enforcing hosts (Fedora/RHEL/CentOS), this means the
  # transport container runs without MAC-layer confinement. The blast radius is
  # limited: the container is rootless and binds only to localhost. For hardened
  # environments that require full SELinux enforcement, see
  # docs/troubleshooting.md for guidance on supplying a custom policy.
  #
  # On non-SELinux hosts (Debian/Ubuntu), this flag is a no-op.
fi

mkdir -p "$DATA_DIR"

# compose.yml files written before TRN-202 always set the retired
# GA_INCLUDE_*_AGENT flags (to "false"), which the new transport rejects at
# startup. compose.yml is regenerated only after the images are built, so a
# failed upgrade would leave the new transport image booting against the old
# file and crash-looping. Strip the retired entries up front.
if [[ -f "${DATA_DIR}/compose.yml" ]] && grep -qE 'GA_INCLUDE_(CLAUDE|CODEX)_AGENT' "${DATA_DIR}/compose.yml"; then
  sed -i.bak -e '/GA_INCLUDE_CLAUDE_AGENT:/d' -e '/GA_INCLUDE_CODEX_AGENT:/d' "${DATA_DIR}/compose.yml" \
    && rm -f "${DATA_DIR}/compose.yml.bak" \
    && echo "✓ Removed retired GA_INCLUDE_* entries from existing compose.yml"
fi

# ga-kiro-auth persists as a plain file under DATA_DIR (ga-kiro-auth),
# written directly by transport itself once a login completes — install.sh
# doesn't need to touch it at all, since the existing -v "${DATA_DIR}:/data"
# mount below already gives transport read/write access to it.
echo "✓ transport data dir ready: ${DATA_DIR}"

# ── API key resolution and exposure check (portal-only-host) ─────────────────
# --api-key > network.api_key > the saved --api-key. DATA_DIR/ga-api-key holds
# the effective key for the ghostship CLI. Runs before any image build or
# container start so an unauthenticated non-loopback install fails fast.
portal_resolve_api_key
portal_check_exposure "$HOST" "$PORT" || exit 1

# ── Resolve dedicated-instance podman command ────────────────────────────────

# On Linux with a dedicated instance, all podman commands (network, pull,
# build, secret, run) must target the dedicated storage root so every
# resource lands on the same instance. On macOS with a dedicated machine,
# use --connection to target it. For the default instance, bare `podman`
# just works. Resolved once and reused below so no step is accidentally
# left targeting the wrong instance.
if [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Linux" ]]; then
  _RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  _STORAGE_ROOT="${HOME}/.local/share/${GA_MACHINE_NAME}/containers/storage"
  _GA_CONTAINERS_CONF="${HOME}/.config/${GA_MACHINE_NAME}/containers.conf"

  # ── WSL2: write a ghostship-scoped containers.conf ────────────────────────
  # Written unconditionally to a ghostship-owned path so it never affects the
  # user's default Podman. On non-WSL2 hosts the file is empty (comment-only),
  # a no-op. The dedicated service unit sets CONTAINERS_CONF to this file.
  mkdir -p "$(dirname "${_GA_CONTAINERS_CONF}")"
  if grep -qi "microsoft" /proc/version 2>/dev/null; then
    # WSL2 doesn't support nftables — ensure iptables is available before
    # writing the config that tells Podman to use it.
    if ! command -v iptables >/dev/null 2>&1; then
      echo "WSL2 detected — installing iptables..."
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get install -y -qq iptables
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y -q iptables
      else
        echo "⚠ Could not install iptables automatically — install it manually before continuing" >&2
      fi
    fi
    cat > "${_GA_CONTAINERS_CONF}" <<CONF_EOF
# ghostship-scoped containers.conf — generated by install.sh
# Scoped to the dedicated '${GA_MACHINE_NAME}' Podman instance only.
# WSL2: use iptables instead of nftables for bridge networking.
[network]
firewall_driver = "iptables"
CONF_EOF
    echo "✓ WSL2 detected — scoped iptables workaround written to ${_GA_CONTAINERS_CONF}"
  else
    cat > "${_GA_CONTAINERS_CONF}" <<CONF_EOF
# ghostship-scoped containers.conf — generated by install.sh
# Scoped to the dedicated '${GA_MACHINE_NAME}' Podman instance only.
CONF_EOF
  fi

  # Prefix CONTAINERS_CONF so all podman subcommands (network, build, run, …)
  # pick up the ghostship-scoped config (WSL2 iptables workaround etc.) without
  # touching the user's default Podman configuration.
  _PODMAN_CMD="env CONTAINERS_CONF=${_GA_CONTAINERS_CONF} podman --root=${_STORAGE_ROOT} --runroot=${_RUNTIME_DIR}/${GA_MACHINE_NAME}-containers"
elif [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Darwin" ]]; then
  _PODMAN_CMD="podman --connection ${GA_MACHINE_NAME}"
else
  _PODMAN_CMD="podman"
fi

# ── Network ───────────────────────────────────────────────────────────────────

${_PODMAN_CMD} network exists ga-portside 2>/dev/null || ${_PODMAN_CMD} network create ga-portside
${_PODMAN_CMD} network exists ga-starboard 2>/dev/null || ${_PODMAN_CMD} network create ga-starboard
if [[ "${GA_DEDICATED_MACHINE}" == "true" ]]; then
  echo "✓ ga-portside and ga-starboard networks ready on dedicated instance '${GA_MACHINE_NAME}' (DNS-enabled by default)"
else
  echo "✓ ga-portside and ga-starboard networks ready (DNS-enabled by default)"
fi

# ── Pre-warm + build images ──────────────────────────────────────────────────


VERSION="$(cat "$GHOSTSHIP_DIR/VERSION")"

# Some build backends (observed with podman) do not reliably invalidate a
# cached layer when only a --build-arg value changes, silently baking a
# stale VERSION into an image whose tag/creation time otherwise look fresh.
# Also detect mid-release source changes within the same VERSION by hashing
# the transport source tree and comparing against the baked label.
# Force --no-cache when either the version or the source hash has changed.
_TRANSPORT_SOURCE_HASH="$(find "$GHOSTSHIP_DIR/transport" -type f | sort | xargs sha256sum 2>/dev/null | sha256sum | awk '{print $1}')"
_TRANSPORT_BUILD_FLAGS=()
if ${_PODMAN_CMD} image exists localhost/transport:latest 2>/dev/null; then
  _baked_transport_version="$(${_PODMAN_CMD} run --rm localhost/transport:latest sh -c 'echo $TRANSPORT_VERSION' 2>/dev/null || true)"
  _baked_transport_hash="$(${_PODMAN_CMD} inspect localhost/transport:latest --format '{{ index .Labels "org.ghostship.source-hash" }}' 2>/dev/null || true)"
  if [[ "$_baked_transport_version" != "$VERSION" ]]; then
    echo "  Detected stale localhost/transport:latest version ('$_baked_transport_version' != '$VERSION') -- forcing a clean rebuild."
    _TRANSPORT_BUILD_FLAGS=(--no-cache)

    # ── Breaking auth change: pre-0.8.0 → 0.8.0+ ──────────────────────────
    # 0.8.0 removes legacy ga-kiro-auth / ga-claude-auth / ga-codex-auth file
    # support. After upgrade, every backend must be re-authenticated with
    # `ghostship auth login <backend>`. Warn the operator and require explicit
    # confirmation before proceeding.
    _minor_new="${VERSION#*.}"; _minor_new="${_minor_new%%.*}"
    _minor_old="${_baked_transport_version#*.}"; _minor_old="${_minor_old%%.*}"
    _major_new="${VERSION%%.*}"
    _major_old="${_baked_transport_version%%.*}"
    if [[ -n "$_baked_transport_version" ]] \
       && { [[ "$_major_old" -lt "$_major_new" ]] \
            || { [[ "$_major_old" -eq "$_major_new" ]] \
                 && [[ "$_minor_old" =~ ^[0-9]+$ ]] && [[ "$_minor_new" =~ ^[0-9]+$ ]] \
                 && [[ "$_minor_old" -lt 8 ]] && [[ "$_minor_new" -ge 8 ]]; }; }; then
      echo ""
      echo "  ╔══════════════════════════════════════════════════════════════════╗"
      echo "  ║  BREAKING CHANGE: Auth credential migration required             ║"
      echo "  ╠══════════════════════════════════════════════════════════════════╣"
      echo "  ║  ghostship 0.8.0 removes support for legacy auth files           ║"
      echo "  ║  (ga-kiro-auth, ga-claude-auth, ga-codex-auth). After upgrade,   ║"
      echo "  ║  crews will return 'not_authenticated' until you re-authenticate: ║"
      echo "  ║                                                                  ║"
      echo "  ║    ghostship auth login kiro                                     ║"
      echo "  ║    ghostship auth login claude   # if using claude backend       ║"
      echo "  ║    ghostship auth login codex    # if using codex backend        ║"
      echo "  ║                                                                  ║"
      echo "  ║  Recommended: uninstall first to purge stale auth files:         ║"
      echo "  ║    ./uninstall.sh --purge-auth && ./install.sh                   ║"
      echo "  ╚══════════════════════════════════════════════════════════════════╝"
      echo ""
      if [[ -t 0 ]]; then
        read -r -p "  Proceed with upgrade? [y/N] " _upgrade_confirm
        case "$_upgrade_confirm" in
          [yY][eE][sS]|[yY]) echo "" ;;
          *)
            echo "Upgrade cancelled. Run './uninstall.sh --purge-auth' first, then re-run install.sh."
            exit 0
            ;;
        esac
      else
        echo "  Non-interactive install: proceeding. Remember to run 'ghostship auth login <backend>' after upgrade."
        echo ""
      fi
    fi
  elif [[ -n "$_baked_transport_hash" && "$_baked_transport_hash" != "$_TRANSPORT_SOURCE_HASH" ]]; then
    echo "  Detected stale localhost/transport:latest source (hash mismatch) -- forcing a clean rebuild."
    _TRANSPORT_BUILD_FLAGS=(--no-cache)
  fi
fi

_CREW_BUILD_FLAGS=()
if ${_PODMAN_CMD} image exists localhost/spec-ops:latest 2>/dev/null; then
  # A changed toolchain list must not reuse a cached toolchain layer.
  _baked_toolchains="$(${_PODMAN_CMD} inspect localhost/spec-ops:latest --format '{{ index .Labels "org.ghostship.toolchains" }}' 2>/dev/null || true)"
  [[ "$_baked_toolchains" == "<no value>" ]] && _baked_toolchains=""
  if [[ "$_baked_toolchains" != "$AGENT_TOOLCHAINS" ]]; then
    echo "  Agent toolchains changed ('${_baked_toolchains}' -> '${AGENT_TOOLCHAINS}') -- forcing a clean rebuild."
    _CREW_BUILD_FLAGS=(--no-cache)
  fi
  _baked_crew_version="$(${_PODMAN_CMD} inspect localhost/spec-ops:latest --format '{{ index .Labels "org.ghostship.version" }}' 2>/dev/null || true)"
  if [[ "$_baked_crew_version" != "${VERSION}-spec-ops" ]]; then
    echo "  Detected stale localhost/spec-ops:latest version ('$_baked_crew_version' != '${VERSION}-spec-ops') -- forcing a clean rebuild."
    _CREW_BUILD_FLAGS=(--no-cache)
  fi
  # TRN-264: a changed .agents pin must also trigger a clean rebuild.
  _baked_agents_ref="$(${_PODMAN_CMD} inspect localhost/spec-ops:latest --format '{{ index .Labels "org.ghostship.agents_ref" }}' 2>/dev/null || true)"
  [[ "$_baked_agents_ref" == "<no value>" ]] && _baked_agents_ref=""
  _effective_agents_ref="${AGENTS_REF:-main}"
  if [[ -n "$_baked_agents_ref" && "$_baked_agents_ref" != "$_effective_agents_ref" ]]; then
    echo "  .agents pin changed ('${_baked_agents_ref}' -> '${_effective_agents_ref}') -- forcing a clean rebuild."
    _CREW_BUILD_FLAGS=(--no-cache)
  fi
fi

echo "Building localhost/base-admission:latest (admission) ..."
# Copy container-side helper scripts into the admission build context so they
# are baked into the crew image at /scripts/. Uses a temp copy to avoid
# polluting the source tree with generated files.
_ADMISSION_CTX="$(mktemp -d)"
cp -r "$GHOSTSHIP_DIR/crews/_base/admission/." "$_ADMISSION_CTX/"
mkdir -p "$_ADMISSION_CTX/container_scripts"
cp "$GHOSTSHIP_DIR/transport/container_scripts/"*.py "$_ADMISSION_CTX/container_scripts/"
${_PODMAN_CMD} build -t localhost/base-admission:latest \
  ${KC_BASE_IMAGE:+--build-arg KC_BASE_IMAGE="${KC_BASE_IMAGE}"} \
  "$_ADMISSION_CTX/" \
  && echo "✓ admission image built" || { echo "✗ admission image build failed"; rm -rf "$_ADMISSION_CTX"; exit 1; }
rm -rf "$_ADMISSION_CTX"

# Worker image — the transport's disposable utility unit for reading
# files/bundles/diffs from STOPPED crew volumes without waking the crew. Based
# on python:3.12.10-slim (shared with the transport image) plus git. Built
# after base-admission and before the crew compositions.
echo "Building localhost/gs-worker:latest (worker) ..."
${_PODMAN_CMD} build -t localhost/gs-worker:latest \
  --build-arg VERSION="${VERSION}" \
  "$GHOSTSHIP_DIR/crews/_worker/" \
  && echo "✓ worker image built" || { echo "✗ worker image build failed"; exit 1; }

echo "Building localhost/spec-ops:latest ..."
${_PODMAN_CMD} build -t localhost/spec-ops-mid:latest \
  "${_CREW_BUILD_FLAGS[@]}" \
  --build-arg VERSION="${VERSION}-spec-ops" \
  --build-arg AGENT_TOOLCHAINS="${AGENT_TOOLCHAINS}" \
  ${AGENTS_REF:+--build-arg AGENTS_REF="${AGENTS_REF}"} \
  "$GHOSTSHIP_DIR/crews/spec-ops/" \
  && ${_PODMAN_CMD} build -t localhost/spec-ops:latest \
  "${_CREW_BUILD_FLAGS[@]}" \
  --build-arg MID_IMAGE=localhost/spec-ops-mid:latest \
  "$GHOSTSHIP_DIR/crews/_base/graduation/" \
  && echo "✓ crew image built" || { echo "✗ crew image build failed"; exit 1; }

echo "Building localhost/transport:latest ..."
${_PODMAN_CMD} build -t localhost/transport:latest \
  "${_TRANSPORT_BUILD_FLAGS[@]}" \
  --build-arg VERSION="${VERSION}" \
  --build-arg SOURCE_HASH="${_TRANSPORT_SOURCE_HASH}" \
  "$GHOSTSHIP_DIR/transport/" \
  && echo "✓ transport image built" || { echo "✗ transport image build failed"; exit 1; }

# ── Podman secret for GA_API_KEY ──────────────────────────────────────────────

${_PODMAN_CMD} secret rm ga-api-key 2>/dev/null || true
GA_SECRET_FLAG=""
if [[ -n "${GA_API_KEY:-}" ]]; then
  printf '%s' "$GA_API_KEY" | ${_PODMAN_CMD} secret create ga-api-key -
  GA_SECRET_FLAG="secrets:\n      - ga-api-key"
  echo "✓ Podman secret 'ga-api-key' created"
fi

# ── Backend credentials are no longer installer-managed (TRN-233) ─────────────
# The four backend credential secrets (ga-crew-anthropic-api-key,
# ga-claude-code-oauth-token, ga-crew-openai-api-key, ga-kiro-api-key) are gone.
# Backend credentials now live in DATA_DIR/credentials/ and are managed with
# `ghostship auth login|logout|status`; the installer has no code path that can
# create, delete or mount a backend credential. uninstall.sh removes any stale
# secrets left over from a pre-change install.

# ── Podman secret for GA_TRANSPORT_SECRET ────────────────────────────────────────
# Idempotent: only generate if the secret does not already exist. This ensures
# the same secret is reused across reinstalls (Caddy and transport stay in sync).
if ! ${_PODMAN_CMD} secret inspect ga-transport-secret >/dev/null 2>&1; then
  openssl rand -hex 32 | ${_PODMAN_CMD} secret create ga-transport-secret -
  echo "✓ Podman secret 'ga-transport-secret' created (new)"
else
  echo "✓ Podman secret 'ga-transport-secret' already exists (keeping existing)"
fi

# ── Copy academy/ and crews/ into the data volume ────────────────────────────
# Snapshot academy/ subdirectories and crews/ from the repo into DATA_DIR so
# the transport container has no runtime dependency on the repo checkout path.
# Changes to these directories require re-running install.sh to take effect.
mkdir -p "${DATA_DIR}/academy"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/agents"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/skills"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/steering"  "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/policies"  "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/orders"    "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/academy/mcp"       "${DATA_DIR}/academy/"
  rsync -a --delete "${GHOSTSHIP_DIR}/crews"             "${DATA_DIR}/"
else
  echo "  rsync not found — falling back to cp (deletions from repo not mirrored until full reinstall)"
  rm -rf "${DATA_DIR}/academy/agents" "${DATA_DIR}/academy/skills" \
         "${DATA_DIR}/academy/steering" "${DATA_DIR}/academy/policies" \
         "${DATA_DIR}/academy/orders" "${DATA_DIR}/academy/mcp" "${DATA_DIR}/crews"
  cp -r "${GHOSTSHIP_DIR}/academy/agents"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/skills"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/steering"  "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/policies"  "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/orders"    "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/academy/mcp"       "${DATA_DIR}/academy/"
  cp -r "${GHOSTSHIP_DIR}/crews"             "${DATA_DIR}/"
fi
echo "✓ academy/ (agents, skills, steering, policies, orders, mcp) and crews/ copied to ${DATA_DIR}"

# ── Generate compose.yml ──────────────────────────────────────────────────────
portal_legacy_bind_notice "${DATA_DIR}/compose.yml" "$HOST" "$PORT"
_PORTAL_BIND="$(portal_addr "$HOST")"
GA_HOST_URL="${GA_HOST_URL:-$(portal_public_base "$HOST" "$PORT")}"

# Written to DATA_DIR so it is machine-specific (socket path, env vars) and
# not committed to the repo. start.sh and uninstall.sh both read it.

# ── Pre-compose validation: GA_ORDERS_DIR ────────────────────────────────────
if [[ -n "${GA_ORDERS_DIR:-}" ]]; then
  if [[ "${GA_ORDERS_DIR}" != /* ]]; then
    echo "✗ GA_ORDERS_DIR=${GA_ORDERS_DIR} is not an absolute path. Set it to an absolute path or leave it unset." >&2
    exit 1
  fi
  if [[ ! -e "${GA_ORDERS_DIR}" ]]; then
    echo "  WARNING: GA_ORDERS_DIR=${GA_ORDERS_DIR} does not exist. The directory will be bind-mounted at runtime; ensure it exists before starting ga-transport." >&2
  fi
fi

# ── Pre-compose validation: TLS cert/key ─────────────────────────────────────
if [[ -n "${GA_TLS_CERTFILE:-}" ]] || [[ -n "${GA_TLS_KEYFILE:-}" ]]; then
  if [[ -z "${GA_TLS_CERTFILE:-}" ]] || [[ -z "${GA_TLS_KEYFILE:-}" ]]; then
    echo "✗ GA_TLS_CERTFILE and GA_TLS_KEYFILE must both be set or both be unset." >&2
    exit 1
  fi
  _cert_dir="$(dirname "${GA_TLS_CERTFILE}")"
  _key_dir="$(dirname "${GA_TLS_KEYFILE}")"
  if [[ "${_cert_dir}" != "${_key_dir}" ]]; then
    echo "✗ GA_TLS_CERTFILE and GA_TLS_KEYFILE must be in the same parent directory." >&2
    echo "  Cert: ${GA_TLS_CERTFILE} (dir: ${_cert_dir})" >&2
    echo "  Key:  ${GA_TLS_KEYFILE} (dir: ${_key_dir})" >&2
    exit 1
  fi
fi

# Pre-compute UI port range end for the compose template.
_DASHBOARD_PORT_START="${GA_DASHBOARD_PORT_RANGE_START:-64058}"
_DASHBOARD_PORT_END=$(( _DASHBOARD_PORT_START + ${GA_DASHBOARD_PORT_RANGE_SIZE:-64} - 1 ))

# compose.yml no longer carries any backend credential; it still holds the
# transport bearer-key secret reference, so create it owner-only. chmod as well,
# because rewriting an existing file keeps its old mode.
_ga_saved_umask="$(umask)"
umask 077
cat > "${DATA_DIR}/compose.yml" <<COMPOSE_EOF
# Generated by install.sh on $(date -u '+%Y-%m-%dT%H:%M:%SZ') — do not edit manually.
# Re-run install.sh to regenerate.
services:
  ga-transport:
    image: localhost/transport:latest
    container_name: ga-transport
    restart: always
    security_opt:
      - label=disable
    networks:
      - ga-portside
      - ga-starboard
    volumes:
      - ${DATA_DIR}:/data
      - ${DATA_DIR}/academy/agents:/agents:ro
      - ${DATA_DIR}/academy/skills:/skills:ro
      - ${DATA_DIR}/academy/steering:/steering:ro
      - ${DATA_DIR}/academy/policies:/policies:ro
      - ${DATA_DIR}/academy/orders:/orders:ro
      - ${DATA_DIR}/academy/mcp:/mcp:ro
      - ${DATA_DIR}/crews:/crews:ro
      - ${PODMAN_SOCK}:${PODMAN_SOCK}
$(if [[ -n "${GA_ORDERS_DIR:-}" ]]; then printf '      - %s:/mnt/orders:ro\n' "${GA_ORDERS_DIR}"; fi)
$(if [[ -n "${GA_TLS_CERTFILE:-}" ]]; then printf '      - %s:/mnt/tls:ro\n' "$(dirname "${GA_TLS_CERTFILE}")"; fi)
    environment:
      PODMAN_SOCKET: ${PODMAN_SOCK}
      GA_TRANSPORT_BIND: "0.0.0.0"
      GA_PORTAL_HOST: "${HOST}"
      GA_API_KEY_DISABLED: "${GA_API_KEY_DISABLED:-}"
      PORT: "64057"
      GA_HOST_URL: "${GA_HOST_URL}"
      GA_MAX_CREWS: "${GA_MAX_CREWS:-20}"
      GA_MAX_ACTIVE_CREWS: "${GA_MAX_ACTIVE_CREWS:-3}"
      GA_IDLE_TIMEOUT_SECS: "${GA_IDLE_TIMEOUT_SECS:-300}"
      GA_SUBAGENT_TIMEOUT_SECS: "${GA_SUBAGENT_TIMEOUT_SECS:-3600}"
      GA_BATCH_MAX_TASKS: "${GA_BATCH_MAX_TASKS:-20}"
      GA_PICKUP_MAX_POLL_SECS: "${GA_PICKUP_MAX_POLL_SECS:-30}"
      GA_CREW_AGENT: "${GA_CREW_AGENT:-kiro}"
      ANTHROPIC_BASE_URL: "${ANTHROPIC_BASE_URL:-}"
      OPENAI_BASE_URL: "${OPENAI_BASE_URL:-}"
      KIRO_IDENTITY_PROVIDER: "${KIRO_IDENTITY_PROVIDER:-}"
      KIRO_REGION: "${KIRO_REGION:-}"
      KC_MODEL_DEFAULT: "${KC_MODEL_DEFAULT:-}"
      KC_MODEL_KIRO_OVERRIDE: "${KC_MODEL_KIRO_OVERRIDE:-}"
      KC_MODEL_KIRO_DEFAULT: "${KC_MODEL_KIRO_DEFAULT:-}"
      KC_MODEL_CLAUDE_OVERRIDE: "${KC_MODEL_CLAUDE_OVERRIDE:-}"
      KC_MODEL_CLAUDE_DEFAULT: "${KC_MODEL_CLAUDE_DEFAULT:-}"
      KC_MODEL_CODEX_OVERRIDE: "${KC_MODEL_CODEX_OVERRIDE:-}"
      KC_MODEL_CODEX_DEFAULT: "${KC_MODEL_CODEX_DEFAULT:-}"
      GA_MIN_FREE_MEM_GB: "${GA_MIN_FREE_MEM_GB:-2.0}"
      GA_SPAWN_MIN_MEMORY_GB: "${GA_SPAWN_MIN_MEMORY_GB:-1.5}"
      GA_RESOURCE_PRESSURE_GB: "${GA_RESOURCE_PRESSURE_GB:-2.0}"
      GA_RESOURCE_CRITICAL_GB: "${GA_RESOURCE_CRITICAL_GB:-1.0}"
      GA_SPAWN_PRESSURE_ESCALATE_CYCLES: "${GA_SPAWN_PRESSURE_ESCALATE_CYCLES:-3}"
      GA_GIT_AUTHOR_NAME: "${GA_GIT_AUTHOR_NAME:-}"
      GA_GIT_AUTHOR_EMAIL: "${GA_GIT_AUTHOR_EMAIL:-}"
      GA_TLS_CERTFILE: "$(if [[ -n "${GA_TLS_CERTFILE:-}" ]]; then echo "/mnt/tls/$(basename "${GA_TLS_CERTFILE}")"; else echo ""; fi)"
      GA_TLS_KEYFILE: "$(if [[ -n "${GA_TLS_KEYFILE:-}" ]]; then echo "/mnt/tls/$(basename "${GA_TLS_KEYFILE}")"; else echo ""; fi)"
      GA_RATE_LIMIT_ENABLED: "${GA_RATE_LIMIT_ENABLED:-true}"
      GA_RATE_LIMIT_LOGIN_GET: "${GA_RATE_LIMIT_LOGIN_GET:-30:60}"
      GA_RATE_LIMIT_LOGIN_POST: "${GA_RATE_LIMIT_LOGIN_POST:-5:300}"
      GA_RATE_LIMIT_MCP: "${GA_RATE_LIMIT_MCP:-300:60}"
      GA_RATE_LIMIT_FILES: "${GA_RATE_LIMIT_FILES:-60:60}"
      GA_RATE_LIMIT_CREW_API: "${GA_RATE_LIMIT_CREW_API:-120:60}"
      GA_RATE_LIMIT_DASHBOARD_AUTH: "${GA_RATE_LIMIT_DASHBOARD_AUTH:-600:60}"
      GA_DASHBOARD_PORT_RANGE_START: "${GA_DASHBOARD_PORT_RANGE_START:-64058}"
      GA_DASHBOARD_DEFAULT: "${GA_DASHBOARD_DEFAULT:-false}"
      GA_DASHBOARD_PORT_RANGE_SIZE: "${GA_DASHBOARD_PORT_RANGE_SIZE:-64}"
      GA_PORTAL_TLS_MODE: "${GA_PORTAL_TLS_MODE:-off}"
      GA_PORTAL_DOMAIN: "${GA_PORTAL_DOMAIN:-}"
      GA_PORTAL_SESSION_TTL_SECS: "${GA_PORTAL_SESSION_TTL_SECS:-86400}"
      GA_ORDERS_DIR: "$(if [[ -n "${GA_ORDERS_DIR:-}" ]]; then echo "/mnt/orders"; else echo ""; fi)"
      KC_IMAGE: "${KC_IMAGE:-localhost/spec-ops:latest}"
    secrets:
      - ga-transport-secret
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '      - ga-api-key\n'; fi)
  ga-portal:
    image: docker.io/caddy:2
    container_name: ga-portal
    restart: always
    ports:
      - "${_PORTAL_BIND}:${PORT:-64057}:${PORT:-64057}"
      - "${_PORTAL_BIND}:${_DASHBOARD_PORT_START}-${_DASHBOARD_PORT_END}:${_DASHBOARD_PORT_START}-${_DASHBOARD_PORT_END}"
    networks:
      - ga-portside
    secrets:
      - ga-transport-secret
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '      - ga-api-key\n'; fi)
    volumes:
      - ${DATA_DIR}/caddy/initial-config.json:/config/initial-config.json:ro
      - ga-portal-data:/data
    command: ["caddy", "run", "--config", "/config/initial-config.json", "--resume"]
networks:
  ga-portside:
    external: true
  ga-starboard:
    external: true
secrets:
  ga-transport-secret:
    external: true
$(if [[ -n "${GA_API_KEY:-}" ]]; then printf '  ga-api-key:\n    external: true\n'; fi)
volumes:
  ga-portal-data:
COMPOSE_EOF
umask "$_ga_saved_umask"
chmod 600 "${DATA_DIR}/compose.yml"

echo "✓ compose.yml written to ${DATA_DIR}/compose.yml"

# ── Generate Caddy initial-config.json ──────────────────────────────────────────
# ga-portal (Caddy) is always installed. This config bootstraps the main-port
# server with Bearer-gated MCP/file routes and the dashboard-auth endpoints.
# Per-crew dashboard servers are added at runtime via the Caddy admin API.
mkdir -p "${DATA_DIR}/caddy"

# Build the TLS stanza based on GA_PORTAL_TLS_MODE.
_AUTO_HTTPS=""  # set to disable auto-HTTPS for TLS_MODE=off
case "${GA_PORTAL_TLS_MODE:-off}" in
  tailscale)
    _TLS_STANZA='"tls": {"automation": {"policies": [{"get_certificate": [{"via": "tailscale"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
  acme)
    _ACME_DOMAIN="${GA_PORTAL_DOMAIN:-}"
    _TLS_STANZA='"tls": {"automation": {"policies": [{"subjects": ["'"${_ACME_DOMAIN}"'"], "issuers": [{"module": "acme"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
  off)
    # Plain HTTP — disable auto-HTTPS, listen on the HTTP port.
    _TLS_STANZA='"tls": {}'
    _MAIN_LISTEN=":${PORT:-64057}"
    _AUTO_HTTPS='"automatic_https": {"disable": true},'
    ;;
  *)  # internal (default)
    _TLS_STANZA='"tls": {"automation": {"policies": [{"issuers": [{"module": "internal"}]}]}}'
    _MAIN_LISTEN=":${PORT:-64057}"
    ;;
esac

# The portal-token header injected on every upstream request.
# Caddy reads the secret from the mounted Podman secret file using the
# {file.<path>} placeholder (Caddy v2.7+).
_PORTAL_TOKEN_HEADER='"headers": {"request": {"set": {"X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"]}}}'

# Build auth routes: gated when GA_API_KEY is set, open passthrough otherwise.
if [[ -n "${GA_API_KEY:-}" ]]; then
  _AUTH_ROUTES=$(cat <<AUTH_EOF
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"], "header": {"Authorization": ["Bearer {file./run/secrets/ga-api-key}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-transport-files-presigned",
              "match": [{"path": ["/files/*"], "query": {"sig": ["*"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"], "header": {"Authorization": ["Bearer {file./run/secrets/ga-api-key}"]}}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-mcp-files-reject",
              "match": [{"path": ["/mcp*", "/files/*"]}],
              "handle": [{"handler": "static_response", "status_code": 401, "headers": {"Www-Authenticate": ["Bearer"]}, "body": "Unauthorized"}]
            },
AUTH_EOF
)
else
  # No API key — pass all routes through to the transport (Tailscale-gated).
  _AUTH_ROUTES=$(cat <<AUTH_EOF
            {
              "@id": "ga-transport-mcp",
              "match": [{"path": ["/mcp*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            },
            {
              "@id": "ga-transport-files",
              "match": [{"path": ["/files/*"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            },
AUTH_EOF
)
fi

# Generate initial-config.json — main server only, no per-crew servers.
cat > "${DATA_DIR}/caddy/initial-config.json" <<CADDY_EOF
{
  "admin": {"listen": "0.0.0.0:2019"},
  "apps": {
    "http": {
      "servers": {
        "ga-main": {
          "listen": ["${_MAIN_LISTEN}"],
          ${_AUTO_HTTPS}
          "routes": [
${_AUTH_ROUTES}
            {
              "@id": "ga-transport-misc",
              "match": [{"path": ["/health", "/version", "/openapi.json", "/dashboard/*", "/login", "/login*", "/logout", "/logout*", "/crews/*/captain/stop"]}],
              "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "ga-transport:64057"}], ${_PORTAL_TOKEN_HEADER}}]
            }
          ]
        }
      }
    },
    ${_TLS_STANZA}
  }
}
CADDY_EOF

echo "✓ Caddy initial-config.json written to ${DATA_DIR}/caddy/initial-config.json"

# Internal CA: surface the root cert path so the operator knows where to
# run 'caddy trust'. The cert lives in the ga-portal-data volume at the
# standard Caddy path /data/caddy/pki/authorities/local/root.crt.
if [[ "${GA_PORTAL_TLS_MODE:-off}" == "internal" ]]; then
  # Resolve the host-side volume mountpoint for ga-portal-data.
  _CADDY_DATA_MOUNTPOINT=""
  # Compose's --project-name ga prefixes the volume (ga_ga-portal-data); the
  # bare name covers older installs.
  for _portal_vol in ga_ga-portal-data ga-portal-data; do
    if ${_PODMAN_CMD} volume exists "${_portal_vol}" 2>/dev/null; then
      _CADDY_DATA_MOUNTPOINT="$(${_PODMAN_CMD} volume inspect "${_portal_vol}" --format '{{.Mountpoint}}' 2>/dev/null || true)"
      break
    fi
  done
  unset _portal_vol
  _CADDY_ROOT_CERT_PATH="${_CADDY_DATA_MOUNTPOINT:-(ga-portal-data not yet created)}/caddy/pki/authorities/local/root.crt"
  echo ""
  echo "── Caddy internal CA ─────────────────────────────────────────────────"
  echo "TLS mode: internal (Caddy built-in CA)"
  echo "Root CA cert: ${_CADDY_ROOT_CERT_PATH}"
  # TRN-268: on macOS the mountpoint is inside the Podman VM — print an extraction hint
  if [[ "$(uname -s)" == "Darwin" ]] && [[ -n "${_CADDY_DATA_MOUNTPOINT}" ]]; then
    echo "  (VM path — to extract to host, run:)"
    echo "    podman machine ssh ${_MACHINE:+${_MACHINE} }cat ${_CADDY_ROOT_CERT_PATH} > ~/ghost-academy-root.crt"
    echo "  Then trust it: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/ghost-academy-root.crt"
  fi
  echo ""
  echo "After ga-portal starts, run this once to trust the CA:"
  echo "  podman exec ga-portal caddy trust"
  echo "or import the cert manually from the path above."
  echo "──────────────────────────────────────────────────────────────────────"
  echo ""
fi

# ── Run transport ─────────────────────────────────────────────────────────────

# Kill any stale rootlessport process that may be holding the transport port
# open from a previous (possibly interrupted) install. These survive container
# removal and will cause compose up to fail with "address already in use".
# ga-transport does not bind a host port (Caddy is the external listener),
# so only check for stale rootlessport on ga-portal's port (PORT).
for _pid in $(pgrep -x rootlessport 2>/dev/null); do
  if ss -tlnp 2>/dev/null | grep -q "0.0.0.0:${PORT:-64057}.*pid=${_pid}"; then
    kill "$_pid" 2>/dev/null && echo "✓ killed stale rootlessport on port ${PORT:-64057} (pid ${_pid})" || true
    sleep 0.5
  fi
done

# The external podman-compose provider is shelled out to as a separate
# process, so CLI flags like --connection or --root/--runroot on the outer
# `podman compose` invocation are NOT inherited by its internal podman calls
# — only environment variables are. Point it at the right instance via
# CONTAINER_HOST for the dedicated Linux instance, or CONTAINER_CONNECTION
# for the dedicated macOS machine (bare `podman` would otherwise resolve via
# whatever the ambient default connection happens to be, which may not be
# '${GA_MACHINE_NAME}'). Non-dedicated installs use the default either way.
if [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Linux" ]]; then
  _COMPOSE_ENV="CONTAINER_HOST=unix://${PODMAN_SOCK}"
elif [[ "${GA_DEDICATED_MACHINE}" == "true" && "$OS" == "Darwin" ]]; then
  _COMPOSE_ENV="CONTAINER_CONNECTION=${GA_MACHINE_NAME}"
else
  _COMPOSE_ENV=""
fi
# Pin the compose provider to podman-compose so Podman cannot select docker-compose
# when both are installed (Podman's default precedence prefers docker-compose).
_COMPOSE_ENV="${_COMPOSE_ENV:+${_COMPOSE_ENV} }PODMAN_COMPOSE_PROVIDER=$(command -v podman-compose)"
eval "${_COMPOSE_ENV} podman rm -f ga-transport" >/dev/null 2>&1 || true
eval "${_COMPOSE_ENV} podman rm -f ga-portal" >/dev/null 2>&1 || true

# Retry loop: transient port conflicts (e.g. macOS ephemeral range overlap with
# the dashboard port space) are typically released within a second or two.
# _COMPOSE_RETRY_ATTEMPTS (3) and _COMPOSE_RETRY_DELAY_SECS (2) are hardcoded.
_compose_attempts="${_COMPOSE_RETRY_ATTEMPTS}"
_compose_delay="${_COMPOSE_RETRY_DELAY_SECS}"
# Guard: treat 0 or non-integer as 1
if ! [[ "${_compose_attempts}" =~ ^[1-9][0-9]*$ ]]; then
  echo "  WARNING: GA_COMPOSE_RETRY_ATTEMPTS='${_compose_attempts}' is not a positive integer — using 1" >&2
  _compose_attempts=1
fi
_compose_ok=0
for _attempt in $(seq 1 "${_compose_attempts}"); do
  if eval "${_COMPOSE_ENV} podman compose --project-name ga -f \"${DATA_DIR}/compose.yml\" up -d --force-recreate --remove-orphans"; then
    _compose_ok=1; break
  fi
  if [[ "${_attempt}" -lt "${_compose_attempts}" ]]; then
    echo "  compose up failed (attempt ${_attempt}/${_compose_attempts}), retrying in ${_compose_delay}s..." >&2
    sleep "${_compose_delay}"
  fi
done
if [[ "${_compose_ok}" -ne 1 ]]; then
  echo "✗ compose up failed after ${_compose_attempts} attempt(s)" >&2
  exit 1
fi
echo "✓ ga-transport container started"

if [[ -n "${GA_API_KEY:-}" ]]; then
  echo "✓ MCP API-key authentication: enabled (see docs/auth.md for client header setup)"
elif [[ "${GA_API_KEY_DISABLED:-}" == "true" ]]; then
  echo "  MCP API-key authentication: disabled (explicit opt-out: network.api_key: false)"
else
  echo "  MCP API-key authentication: disabled (loopback-only; pass --api-key <key> to enable)"
fi

sleep 1  # brief pause before first probe attempt
echo ""
echo "=== Health check ==="
_max_wait=90
_interval=3
_ready=0
_caddy_scheme="http"
[[ "${GA_PORTAL_TLS_MODE:-off}" != "off" ]] && _caddy_scheme="https"
# Ready means /health answers THROUGH ga-portal at its published address — the
# path every client uses. A transport that answers only inside its own
# container (e.g. Caddy cannot reach it) is not ready.
_probe_url="$(portal_probe_base "$HOST" "${PORT:-64057}" "$_caddy_scheme")/health"
for (( _i=0; _i<_max_wait; _i+=_interval )); do
  if curl -sfk "$_probe_url" >/dev/null 2>&1; then
    _ready=1
    break
  fi
  sleep "$_interval"
done
if [[ "$_ready" == "1" ]]; then
  echo "✓ Transport is ready (${_probe_url})"
else
  echo "✗ Transport did not become ready through ga-portal within ${_max_wait}s (${_probe_url})" >&2
  # Diagnostic only: does the transport answer inside its own container? It
  # always listens on 64057 there, whatever PORT is.
  if ${_PODMAN_CMD} exec ga-transport python3 -c "
import urllib.request, os
secret = open('/run/secrets/ga-transport-secret').read().strip() if os.path.exists('/run/secrets/ga-transport-secret') else ''
req = urllib.request.Request('http://127.0.0.1:64057/health', headers={'X-Transport-Token': secret})
urllib.request.urlopen(req)
" >/dev/null 2>&1; then
    echo "  ga-transport is up, but ga-portal cannot reach it (portal-to-transport path)." >&2
    echo "  Last 20 lines of ga-portal logs:" >&2
    ${_PODMAN_CMD} logs ga-portal --tail 20 >&2
  else
    echo "  Last 20 lines of container logs:" >&2
    ${_PODMAN_CMD} logs ga-transport --tail 20 >&2
  fi
  exit 1
fi

# ── Interactive-mode authentication (TRN-233) ────────────────────────────────
# After the transport is ready, offer `ghostship auth login <backend>` for each
# ENABLED backend (from GA_CREW_AGENT) that the transport reports as not yet
# configured. Credentials are never collected by the installer — the CLI drives
# the login against the just-installed URL and bearer key (discovered via the
# same Podman inspect `ghostship status` uses), so no flags are needed here.
if [[ "${_INTERACTIVE_MODE:-false}" == "true" ]]; then
    echo ""
    echo "=== Authentication ==="

    # Which enabled backends still need a credential? Ask the transport; its
    # `GET /login/<backend>` reports {"configured": bool} per backend. If the
    # status call fails (older transport, transient error), fall back to
    # offering a login for every enabled backend rather than skipping auth.
    _enabled_backends="${GA_CREW_AGENT//,/ }"
    _auth_status_json="$("${GHOSTSHIP_DIR}/ghostship" auth status --json 2>/dev/null || true)"
    for _backend in $_enabled_backends; do
        _backend="${_backend// /}"
        [[ -z "$_backend" ]] && continue
        _is_configured="unknown"
        if [[ -n "$_auth_status_json" ]]; then
            _is_configured="$(printf '%s' "$_auth_status_json" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print('unknown'); sys.exit(0)
info = data.get('$_backend') or {}
print('yes' if info.get('configured') else 'no')
" 2>/dev/null || echo unknown)"
        fi
        if [[ "$_is_configured" == "yes" ]]; then
            echo "  ${_backend}: already configured — skipping login."
        else
            echo "  ${_backend}: starting login (run 'ghostship auth logout ${_backend}' to undo)."
            "${GHOSTSHIP_DIR}/ghostship" auth login "${_backend}" || \
                echo "  ${_backend}: login not completed — run 'ghostship auth login ${_backend}' later." >&2
        fi
    done
    unset _enabled_backends _auth_status_json _backend _is_configured
fi

echo ""
echo "=== Post-install ==="

# ── Best-effort ga-net cleanup ────────────────────────────────────────────────
# If ga-net exists and has no containers, remove it (migration complete).
# This is a no-op on fresh installs. Silently skipped if the network still
# has containers (migration will run at transport startup via _reconcile_registry).
if ${_PODMAN_CMD} network exists ga-net 2>/dev/null; then
  _ga_net_containers="$(${_PODMAN_CMD} network inspect ga-net --format '{{len .Containers}}' 2>/dev/null || echo "1")"
  if [[ "${_ga_net_containers}" == "0" ]]; then
    ${_PODMAN_CMD} network rm ga-net >/dev/null 2>&1 \
      && echo "✓ ga-net removed (empty, migration complete)" \
      || echo "  ga-net removal skipped (in use or error)"
  else
    echo "  ga-net still has ${_ga_net_containers} container(s) — will be migrated at transport startup"
  fi
fi
# ── Interactive-mode harness registration (TRN-255) ──────────────────────────
# Always run ghostship setup after a successful wizard install — no prompt.
# Non-fatal: missing agent clients are reported per-agent but do not fail the install.
if [[ "${_INTERACTIVE_MODE:-false}" == "true" ]]; then
    echo ""
    echo "Registering MCP server with detected agent clients (kiro-cli, claude, opencode)..."
    "${GHOSTSHIP_DIR}/ghostship" setup || \
        echo "  ⚠ ghostship setup encountered an issue — run 'ghostship setup' manually if needed."
fi

# The manual post-install instructions below are only relevant to the
# non-interactive path; interactive mode handled auth and registration above.
if [[ "${_INTERACTIVE_MODE:-false}" != "true" ]]; then
echo "Register the MCP server (one-time):"
echo "  kiro-cli mcp add --name ghostship --url ${GA_HOST_URL%/}/mcp --scope global"
echo ""
echo "Then from Kiro CLI, create the first crew:"
echo "  ghostship__launch(crew_id=\"general\")"
echo ""
echo "On first launch you'll be prompted to authenticate kiro-cli inside the"
echo "crew container. Open the returned URL, then call launch again with the"
echo "same crew_id to finish setup."
fi

# ── Make ghostship available on PATH ─────────────────────────────────────────
_LOCAL_BIN="${HOME}/.local/bin"
mkdir -p "${_LOCAL_BIN}"
ln -sf "${GHOSTSHIP_DIR}/ghostship" "${_LOCAL_BIN}/ghostship"
echo ""
echo "✓ ghostship CLI linked to ${_LOCAL_BIN}/ghostship"
if [[ ":${PATH}:" != *":${_LOCAL_BIN}:"* ]]; then
  echo "  Add ~/.local/bin to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
