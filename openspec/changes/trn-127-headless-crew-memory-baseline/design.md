## Context

`_patch_crew_config` in `transport/lifecycle.py` writes a `config.local.json`
into each crew container at launch. KiroCrew deep-merges this over its own
`config.json` on every gateway start. Currently the patch only covers the
`agent` section:

```python
agent_overrides: dict[str, Any] = {
    "agent": GA_CREW_AGENT,
    "spawn_min_memory_gb": GA_SPAWN_MIN_MEMORY_GB,
    "resource_pressure_gb": GA_RESOURCE_PRESSURE_GB,
    "resource_critical_gb": GA_RESOURCE_CRITICAL_GB,
    "dangerously_skip_permissions": True,
    "default_agent": "ghost",
    "reasoning_effort": "max",
    "subagent_timeout_secs": GA_SUBAGENT_TIMEOUT_SECS,
    "subagent_max_turns": GA_SUBAGENT_MAX_TURNS,
    "sandbox": "off",
}
```

The `patch_crew_config.py` container script receives this dict as JSON on
stdin and writes `{"agent": <agent_overrides>}` to `config.local.json`.
It does not currently support writing to other top-level config sections.

## Goals / Non-Goals

**Goals:**
- Extend `patch_crew_config.py` to accept and deep-merge a full config
  structure (not just the `agent` section)
- Add `stt`, `session`, `telemetry`, and top-level overrides to
  `_patch_crew_config` in `lifecycle.py`
- Unit test that each new section lands in `config.local.json` correctly

**Non-Goals:**
- Exposing the new keys as env-var-configurable transport config — these are
  fixed headless-optimised values, not operator-tunable
- Changing any `agent`-section keys already applied
- Adding the `watchdog_rss_max_mb` value as a transport config variable
  (hardcoded at 600 MB is fine for now)

## Decisions

### D1: Fixed values, not env-var configurable

The new keys (`stt.enabled`, `session.eager_spawn`, etc.) are always `false`
or a fixed value for a headless crew. There is no use case for an operator
enabling STT or eager spawn on a server deployment, so they are not surfaced
as `GA_*` env vars. If an operator needs to override them they can modify
`_patch_crew_config` directly.

### D2: `patch_crew_config.py` accepts full config dict

Rather than adding per-section arguments, the script is extended to accept
a complete config override dict. The caller (`_patch_crew_config` in
`lifecycle.py`) builds the full structure and passes it as a single JSON
argument. This is the simplest extension that does not break the existing
agent-section path.

```python
full_overrides = {
    "agent": agent_overrides,
    "stt": {"enabled": False},
    "session": {
        "eager_spawn": False,
        "timeout_secs": 300,
        "watchdog_rss_max_mb": 2000,
    },
    "telemetry": {"beacon_enabled": False},
    "auto_update": False,
}
```

### D3: `watchdog_rss_max_mb = 2000`

2000 MB (2 GB) is set as the per-session RSS ceiling. Measured active task
peak for normal file-scan work is ~1.9 GB; an intensive Banshee review on a
large codebase is expected to approach or exceed this. The watchdog is
intentionally set above normal peak load — its purpose is to catch runaway
accumulation across many sequential tasks on a long-lived crew, not to kill
a healthy active session mid-task. A 600 MB ceiling (initial draft) would
have recycled nearly every real task. If 2 GB proves insufficient headroom
for the worst-case Banshee sessions it can be raised; it is not
user-configurable in this change (see D1).

## Migration Plan

1. Extend `patch_crew_config.py` to deep-merge arbitrary top-level sections.
2. Update `_patch_crew_config` in `lifecycle.py` to pass the full override dict.
3. Add unit tests.
4. Deploy — new overrides take effect on the next crew launch. Existing crews
   are unaffected until they are nuked and relaunched.
5. Measure idle RSS on a freshly launched crew to confirm ~160 MB baseline.
