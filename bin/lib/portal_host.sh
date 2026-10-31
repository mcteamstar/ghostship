#!/usr/bin/env bash
# portal_host.sh — bash shims for install.sh / start.sh / test_portal_host.py.
#
# All HOST / API-key logic lives in portal_host.py. These shims delegate to it
# so callers that source this file and invoke the shell functions continue to
# work without change.
#
# Source this file; it defines functions only and has no side effects.

_PORTAL_HOST_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/portal_host.py"
_PORTAL_HOST_VENDOR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/vendor"

# Succeed when HOST is a loopback address (unset, localhost, ::1, 127.0.0.0/8).
portal_is_loopback() {
  [[ "$(PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" is_loopback "${1:-}")" == "true" ]]
}

# Succeed when HOST binds every interface.
portal_is_wildcard() {
  [[ "$(PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" is_wildcard "${1:-}")" == "true" ]]
}

# Print HOST in URL/port-mapping form: IPv6 literals bracketed.
portal_addr() {
  PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" addr "${1:-}"
}

# Print the default public base URL: localhost for loopback/wildcard HOST,
# otherwise the HOST itself.
portal_public_base() {
  PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" public_base "${1:-}" "${2:-}"
}

# Print the base URL readiness probes use to reach the portal from this host.
portal_probe_base() {
  PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" probe_base "${1:-}" "${2:-}" "${3:-http}"
}

# Resolve the endpoint API key.
# Reads:  API_KEY_FLAG_PASSED, _FLAG_API_KEY, GA_API_KEY, GA_API_KEY_DISABLED,
#         GA_API_KEY_SOURCE, GA_API_KEY_DEPRECATED_OFF, DATA_DIR
# Sets:   GA_API_KEY, GA_API_KEY_DISABLED
# Writes: DATA_DIR/ga-api-key.flag and DATA_DIR/ga-api-key
portal_resolve_api_key() {
  local _result
  _result="$(PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" resolve_api_key \
    "${DATA_DIR:-}" \
    "${API_KEY_FLAG_PASSED:-0}" \
    "${_FLAG_API_KEY:-}" \
    "${GA_API_KEY:-}" \
    "${GA_API_KEY_DISABLED:-}" \
    "${GA_API_KEY_SOURCE:-}" \
    "${GA_API_KEY_DEPRECATED_OFF:-}"
  )"
  # Parse the two output lines: GA_API_KEY=<value> and GA_API_KEY_DISABLED=<value>
  GA_API_KEY="${_result#*GA_API_KEY=}"
  GA_API_KEY="${GA_API_KEY%%$'\n'*}"
  local _second="${_result#*$'\n'}"
  GA_API_KEY_DISABLED="${_second#*GA_API_KEY_DISABLED=}"
}

# Refuse to publish an unauthenticated portal beyond loopback.
# Usage: portal_check_exposure HOST PORT   (reads GA_API_KEY, GA_API_KEY_DISABLED)
portal_check_exposure() {
  GA_API_KEY="${GA_API_KEY:-}" GA_API_KEY_DISABLED="${GA_API_KEY_DISABLED:-}" \
    PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" check_exposure "${1:-}" "${2:-}"
}

# Print a one-time notice when an existing compose.yml published ga-portal on
# all interfaces but HOST now keeps it on loopback (the HOST default changed).
# Usage: portal_legacy_bind_notice COMPOSE_PATH HOST PORT
portal_legacy_bind_notice() {
  PYTHONPATH="$_PORTAL_HOST_VENDOR" python3 "$_PORTAL_HOST_PY" legacy_bind_notice "${1:-}" "${2:-}" "${3:-}"
}
