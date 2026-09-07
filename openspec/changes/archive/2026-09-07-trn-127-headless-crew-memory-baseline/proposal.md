## Why

KiroCrew 0.5.0 enables several features by default that are unused and wasteful
in a headless spec-ops crew: Whisper STT (no microphone), eager session process
spawning (no interactive user), a 1-hour session idle timeout, telemetry beacon,
and auto-update.

Measured on vm23 (2026-09-07):

| State | RSS per crew |
|---|---|
| Idle (current) | ~470 MB |
| Active task peak | ~1.5–1.9 GB |
| Post-task retained | ~1.2–1.6 GB |

The ~470 MB idle figure breaks down as: KiroCrew gateway (~160 MB) + one
eagerly pre-spawned `kiro-cli-chat` process (~340 MB) forked at startup
regardless of whether any task is running. Disabling `session.eager_spawn`
eliminates that pre-fork; `stt.enabled = false` removes the Whisper model.

Projected idle baseline after this change: **~160 MB** (gateway only).
Session processes spawn on first dispatch and are reaped within 5 minutes
of task completion (down from 60 minutes).

## What Changes

- `session.eager_spawn = false` — stop pre-forking `kiro-cli-chat` at startup. Session process spawns on first task instead (+2–5s first-dispatch latency; acceptable for dispatch-based use).
- `session.timeout_secs = 300` — reclaim session memory 12× faster after a task completes (was 3600s / 1 hour).
- `session.watchdog_rss_max_mb = 2000` — new in 0.5.0; hard RSS ceiling per session process. Recycles the session if exceeded, preventing unbounded memory accumulation across multiple tasks on a long-lived crew. Set above the ~1.9 GB active task peak to avoid recycling healthy sessions.
- `stt.enabled = false` — disable Whisper STT. No microphone in a headless server crew; the base model (~148 MB) is loaded unnecessarily.
- `telemetry.beacon_enabled = false` — suppress outbound beacon ping. Network hygiene for server deployments.
- `auto_update = false` — prevent KiroCrew from self-updating inside a container pinned to a specific image version.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: The config.local.json patch applied at crew launch (`_patch_crew_config`) is extended from agent-scoped keys only to cover `stt`, `session`, `telemetry`, and top-level keys. The patch script gains the ability to deep-merge arbitrary top-level sections, not just `agent`.

## Impact

- `transport/lifecycle.py` — `_patch_crew_config`: extend `agent_overrides` to a full nested config structure
- `transport/container_scripts/patch_crew_config.py` — extend deep-merge to handle arbitrary top-level sections beyond `agent`
- `tests/unit/test_lifecycle.py` — add tests for new config sections being written correctly
- `docs/configuration.md` — document the new default overrides and the `session.watchdog_rss_max_mb` safety net
