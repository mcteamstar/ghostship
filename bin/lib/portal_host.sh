#!/usr/bin/env bash
# Shared HOST / API-key handling for install.sh, start.sh and their tests
# (portal-only-host).
#
# HOST is the address ga-portal (Caddy) publishes on — nothing else. The
# transport always listens on 0.0.0.0 inside its container and is reached by
# Caddy as ga-transport:64057. Every exposure decision here is therefore about
# the portal's published address, never the transport's listen address.
#
# The loopback test is yaml_config.py's `is-loopback` (stdlib-only), the same
# logic transport/config.py uses at startup, so install time and runtime agree.
#
# Source this file; it defines functions only and has no side effects.

_portal_host_helper() {
  printf '%s/yaml_config.py' "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
}

# Succeed when HOST is a loopback address (unset, localhost, ::1, 127.0.0.0/8).
portal_is_loopback() {
  [[ "$(python3 "$(_portal_host_helper)" is-loopback "${1:-}")" == "true" ]]
}

# Succeed when HOST binds every interface.
portal_is_wildcard() {
  case "${1:-}" in
    0.0.0.0|::|"[::]") return 0 ;;
    *) return 1 ;;
  esac
}

# Print HOST in URL/port-mapping form: IPv6 literals bracketed.
portal_addr() {
  local host="${1:-127.0.0.1}"
  if [[ "$host" == *:* && "$host" != \[* ]]; then
    printf '[%s]' "$host"
  else
    printf '%s' "$host"
  fi
}

# Print the default public base URL (GA_HOST_URL when unset): localhost for a
# loopback or wildcard HOST, otherwise the HOST itself.
portal_public_base() {
  local host="${1:-}" port="$2"
  if [[ -z "$host" ]] || portal_is_wildcard "$host" || portal_is_loopback "$host"; then
    printf 'http://localhost:%s' "$port"
  else
    printf 'http://%s:%s' "$(portal_addr "$host")" "$port"
  fi
}

# Print the base URL readiness probes use to reach the portal from this host.
# A wildcard HOST is reached via 127.0.0.1; anything else at its own address.
portal_probe_base() {
  local host="${1:-}" port="$2" scheme="${3:-http}"
  if [[ -z "$host" ]] || portal_is_wildcard "$host"; then
    host="127.0.0.1"
  fi
  printf '%s://%s:%s' "$scheme" "$(portal_addr "$host")" "$port"
}

# Resolve the endpoint API key. Order: --api-key flag > network.api_key in the
# YAML > the key last passed with --api-key (DATA_DIR/ga-api-key.flag).
#
# Reads:  API_KEY_FLAG_PASSED, _FLAG_API_KEY, GA_API_KEY, GA_API_KEY_DISABLED,
#         GA_API_KEY_SOURCE, GA_API_KEY_DEPRECATED_OFF, DATA_DIR
# Sets:   GA_API_KEY, GA_API_KEY_DISABLED
# Writes: DATA_DIR/ga-api-key.flag — the --api-key input (empty = none given)
#         DATA_DIR/ga-api-key      — the effective key, read by the ghostship
#                                    CLI; removed when there is no key.
portal_resolve_api_key() {
  local flag_file="${DATA_DIR}/ga-api-key.flag"
  local effective="${DATA_DIR}/ga-api-key"

  # One-time migration: before portal-only-host, ga-api-key was written only by
  # --api-key. The .flag file always exists afterwards (empty when no flag key),
  # so this never re-runs and never mistakes a YAML key for a flag key.
  if [[ ! -e "$flag_file" ]]; then
    if [[ -s "$effective" ]]; then
      (umask 077; cp "$effective" "$flag_file")
    else
      (umask 077; : > "$flag_file")
    fi
  fi

  if [[ "${API_KEY_FLAG_PASSED:-0}" == "1" ]]; then
    if [[ -n "${_FLAG_API_KEY:-}" ]]; then
      (umask 077; printf '%s' "$_FLAG_API_KEY" > "$flag_file")
      echo "✓ API key from --api-key saved to ${flag_file} (reused on future installs)"
    else
      (umask 077; : > "$flag_file")
      echo "✓ Saved --api-key cleared"
    fi
    chmod 600 "$flag_file"
  fi

  if [[ "${API_KEY_FLAG_PASSED:-0}" == "1" && -n "${_FLAG_API_KEY:-}" ]]; then
    GA_API_KEY="$_FLAG_API_KEY"
    GA_API_KEY_DISABLED=""
  elif [[ "${GA_API_KEY_SOURCE:-}" == "yaml" ]]; then
    : # network.api_key already set GA_API_KEY or GA_API_KEY_DISABLED
  elif [[ -s "$flag_file" ]]; then
    GA_API_KEY="$(cat "$flag_file")"
    GA_API_KEY_DISABLED=""
    echo "✓ API key restored from ${flag_file}"
  else
    GA_API_KEY=""
  fi

  # Deprecated network.require_api_key: off — an opt-out only when no key was
  # resolved from any source, so a leftover setting never disables a real key.
  if [[ -z "${GA_API_KEY:-}" && "${GA_API_KEY_DEPRECATED_OFF:-}" == "true" ]]; then
    GA_API_KEY_DISABLED="true"
  fi

  if [[ -n "${GA_API_KEY:-}" ]]; then
    (umask 077; printf '%s' "$GA_API_KEY" > "$effective")
    chmod 600 "$effective"
  else
    rm -f "$effective"
  fi
}

# Refuse to publish an unauthenticated portal beyond loopback unless the
# operator opted out explicitly with network.api_key: false.
# Usage: portal_check_exposure HOST PORT   (reads GA_API_KEY, GA_API_KEY_DISABLED)
portal_check_exposure() {
  local host="${1:-}" port="$2"
  portal_is_loopback "$host" && return 0
  [[ -n "${GA_API_KEY:-}" ]] && return 0
  local where
  where="$(portal_addr "$host"):${port}"
  if [[ "${GA_API_KEY_DISABLED:-}" == "true" ]]; then
    echo "WARNING: ga-portal is published on ${where} with authentication explicitly disabled (network.api_key: false) — anyone who can reach that address can use every MCP tool." >&2
    return 0
  fi
  cat >&2 <<EOF
WARNING: ga-portal would be published on ${where} with no API key — anyone who can reach that address could use every MCP tool.
Aborting. Fix one of:
  - set an API key: --api-key <key>, or network.api_key in config/ghostship.yaml
  - keep it local: network.host: 127.0.0.1
  - accept unauthenticated access (e.g. behind your own auth proxy): network.api_key: false
EOF
  return 1
}

# Print a one-time notice when an existing compose.yml published ga-portal on
# all interfaces but HOST now keeps it on loopback (the HOST default changed).
# Usage: portal_legacy_bind_notice COMPOSE_PATH HOST PORT
portal_legacy_bind_notice() {
  local compose="$1" host="${2:-}" port="$3"
  [[ -f "$compose" ]] || return 0
  portal_is_loopback "$host" || return 0
  grep -q "\"0\.0\.0\.0:${port}:" "$compose" || return 0
  echo "ℹ ga-portal was published on all interfaces (0.0.0.0:${port}); it is now loopback-only (${host:-127.0.0.1})." >&2
  echo "  HOST now defaults to 127.0.0.1. For remote access set network.host in config/ghostship.yaml" >&2
  echo "  (plus network.api_key, or network.api_key: false to opt out of authentication)." >&2
}
