# Design

## Context

`scripts/install.sh` runs `podman compose up -d --force-recreate --remove-orphans` at line ~1068. There is no retry — a non-zero exit code causes `set -eo pipefail` to abort immediately. The most common transient failure is `address already in use` from an ephemeral port collision in the dashboard port range; the port is typically released within 1–2 seconds.

The companion fix (reducing `GA_DASHBOARD_PORT_RANGE_SIZE` from 1024 to 64, commit `660ae48`) reduces the probability of collision but does not eliminate it.

## Goals / Non-Goals

**Goals:**
- Retry `compose up` up to N times with a short sleep, covering the transient-port case
- Make N and the sleep delay configurable via `ghostship.conf`
- Document both vars in `docs/configuration.md` and `config/ghostship.conf.example`
- Add a test covering the retry path

**Non-Goals:**
- Retrying other install steps (image builds, machine init, health check)
- Detecting specific failure types — retry fires on any non-zero compose exit
- Changing the health check timeout or probe logic

## Decisions

**Inline retry loop in bash, not a helper function**

The compose up invocation is a single call site. A local `for` loop is simpler than a generic retry helper and keeps the diff minimal. The loop captures compose stderr to print on final failure.

```bash
_compose_attempts="${GA_COMPOSE_RETRY_ATTEMPTS:-3}"
_compose_delay="${GA_COMPOSE_RETRY_DELAY_SECS:-2}"
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
```

`set -eo pipefail` means the `if` wrapper is needed to prevent the loop body from aborting on compose failure; the `if` suppresses the exit code and lets the loop control flow handle it.

**Config-file-only vars, no CLI flags**

Following the established pattern in this project: `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` are resolved from `ghostship.conf` only, with no CLI flag equivalents. Operators who want to tune them edit their config file.

**No minimum validation on GA_COMPOSE_RETRY_ATTEMPTS**

Setting it to 0 or a non-integer would cause `seq 1 0` to produce no output (zero attempts, immediate failure). Document that valid range is ≥ 1 and treat 0 as "set to 1" with a warning, to avoid a confusing silent no-op.

## Risks / Trade-offs

**Masking persistent failures** → The retry adds at most `(N-1) × delay` seconds before surfacing a real error. With defaults (3 attempts, 2s delay) that's 4 extra seconds — acceptable.

**start.sh does not get the same retry** — `start.sh` also calls `compose up -d` (without `--force-recreate`). The same transient port conflict can occur there. However, `start.sh` is a no-op if the service is already running, and port conflicts there are less likely since no dashboard ports are being freshly allocated. Out of scope for this change; can be addressed separately if it becomes a reported issue.
