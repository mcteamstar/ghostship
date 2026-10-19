#!/usr/bin/env bash
# Shared GA_AGENT_BACKENDS parsing for install.sh and its tests (TRN-202).
#
# Applies the same rules as parse_agent_backends() in transport/config.py:
# split on commas, trim, lowercase, drop empty entries, duplicates and kiro
# (always enabled). Validation differs by side: the transport checks its known
# backends, this file checks the toolchain scripts present, so install.sh never
# holds a backend list of its own. tests/unit/test_agent_backends_parity.py
# keeps the two in step.
#
# Source this file; it defines functions only and has no side effects.

# Print the normalised optional backends, comma-separated, first-listed order.
agent_backends_normalise() {
  local raw="${1:-}" entry name out="" entries=()
  # `read` stops at a newline, which would silently drop later entries. The
  # transport rejects the same input, so reject it here too.
  if [[ "$raw" == *$'\n'* || "$raw" == *$'\r'* ]]; then
    echo "✗ GA_AGENT_BACKENDS must be a single line (found a line break)." >&2
    return 1
  fi
  # read -a splits without pathname expansion, so '*' or '?' stay literal.
  IFS=',' read -r -a entries <<< "$raw"
  for entry in ${entries[@]+"${entries[@]}"}; do
    name="$(printf '%s' "$entry" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    [[ -z "$name" || "$name" == "kiro" ]] && continue
    case ",$out," in *",$name,"*) continue ;; esac
    out="${out:+$out,}$name"
  done
  printf '%s' "$out"
}

# Print the available optional toolchains (script basenames), comma-separated.
agent_backends_available() {
  local dir="$1" script out=""
  for script in "$dir"/*.sh; do
    [[ -f "$script" ]] || continue
    script="$(basename "$script" .sh)"
    out="${out:+$out,}$script"
  done
  printf '%s' "$out"
}

# Validate a normalised list against the toolchain scripts in $2.
# Names must match ^[a-z][a-z0-9-]*$ and be a script basename, so a path-like
# name can never select a script outside the toolchains directory.
agent_backends_validate() {
  local list="$1" dir="$2" available name names=()
  available="$(agent_backends_available "$dir")"
  IFS=',' read -r -a names <<< "$list"
  for name in ${names[@]+"${names[@]}"}; do
    if [[ ! "$name" =~ ^[a-z][a-z0-9-]*$ ]] || [[ ",$available," != *",$name,"* ]]; then
      echo "✗ GA_AGENT_BACKENDS contains unknown backend '$name'. Available: kiro${available:+,$available}." >&2
      return 1
    fi
  done
}

# Require the default backend to be kiro or a member of the normalised list.
# Trims and lowercases like the transport. $3 (optional) is the toolchains
# directory, used to tell a typo from a backend that just isn't enabled.
agent_backends_check_default() {
  local default="${1:-kiro}" list="$2" dir="${3:-}" available
  default="$(printf '%s' "$default" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  [[ -z "$default" ]] && default="kiro"
  [[ "$default" == "kiro" || ",$list," == *",$default,"* ]] && return 0
  if [[ -n "$dir" ]]; then
    available="$(agent_backends_available "$dir")"
    if [[ ",$available," != *",$default,"* ]]; then
      echo "✗ GA_CREW_ACP_BACKEND='$default' is not a known backend. Valid: kiro${available:+,$available}." >&2
      return 1
    fi
  fi
  echo "✗ GA_CREW_ACP_BACKEND='$default' is not enabled. Add it to GA_AGENT_BACKENDS (enabled: kiro${list:+,$list}), then re-run ghostship install." >&2
  return 1
}

# Fail on the retired GA_INCLUDE_*_AGENT flags (any non-empty value).
agent_backends_reject_retired() {
  local name
  for name in GA_INCLUDE_CLAUDE_AGENT GA_INCLUDE_CODEX_AGENT; do
    if [[ -n "${!name:-}" ]]; then
      echo "✗ $name is retired. Enable backends with GA_AGENT_BACKENDS (for example GA_AGENT_BACKENDS=claude) instead." >&2
      return 1
    fi
  done
}
