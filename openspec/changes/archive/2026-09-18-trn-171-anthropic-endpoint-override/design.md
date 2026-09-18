## Context

Claude Code reads `ANTHROPIC_BASE_URL` from its environment natively — no code changes inside the container are needed. The entire change is on the ghostship transport side: read the config var, pass it through to the container environment at `launch` time.

The injection site is `server.py`'s `launch()` function, in the same `container_env` block that already conditionally injects `ANTHROPIC_API_KEY` when `GA_CREW_ACP_BACKEND=claude`. This is a one-liner addition.

## Goals / Non-Goals

**Goals:**
- Operators can redirect Claude-backend crew traffic to any Anthropic-compatible endpoint via `GA_CREW_ANTHROPIC_BASE_URL`
- Default behaviour (no var set) is unchanged

**Non-Goals:**
- Per-crew endpoint override (transport-wide, same as other Claude backend settings)
- Validating the URL format at startup (let Claude Code report the error at session time)
- Supporting endpoint override for non-Claude backends

## Decisions

### D1: Inject at container creation time, not as a Podman secret

`ANTHROPIC_API_KEY` is already injected as a plain env var. `ANTHROPIC_BASE_URL` is not a secret — it's a non-sensitive config value. Plain env var is the right choice, consistent with the existing pattern.

### D2: No startup validation of the URL

The value is passed through as-is. An invalid URL will produce an error from Claude Code at session time with a clear message. Adding URL validation at startup would add complexity for marginal benefit.

### D3: Update the WARNING log to name the effective endpoint

The existing WARNING at `_finish_crew_setup` says "crew requires outbound access to api.anthropic.com". When `GA_CREW_ANTHROPIC_BASE_URL` is set, the warning should name the override instead. This keeps the log accurate and helps operators confirm their config is applied.

## Migration

Existing Claude-backend operators: no action required. The var is unset by default; behaviour is unchanged.

To use a local router: add `GA_CREW_ANTHROPIC_BASE_URL=http://your-router/v1` to `ghostship.conf` and restart the transport (`ghostship stop && ghostship start`). No image rebuild needed.
