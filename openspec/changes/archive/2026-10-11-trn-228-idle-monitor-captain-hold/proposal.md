# Proposal

## Why

In 0.5.x, Captain check-ins ran as KiroCrew gateway cron jobs. The idle monitor held crews alive by consulting `/api/crons` — an enabled cron job was a standing commitment that blocked idle-stop. In 0.6.0, Captain moved to a transport-side dispatch+steer model with no gateway cron job. The idle monitor was not updated to account for this: it still only checks `/api/crons` (now empty for Captain crews) and active spawn tasks (also empty between check-ins). A crew with an enabled Captain schedule but no in-flight work gets idle-stopped on schedule. The `_captain_monitor` then tries to restart it before the next check-in, but the restart→steer path is fragile and fails silently, causing Captain to stall indefinitely.

## What Changes

- `transport/monitors.py` (`_idle_monitor`): check registry-side captain schedule entries before stopping a crew. An enabled captain entry with a real `next_fire_at` counts as a standing commitment — same semantics as an enabled gateway cron.
- `openspec/specs/idle-and-recovery/spec.md`: extend the "Idle container stop" requirement to explicitly cover transport-side captain schedule entries alongside gateway cron jobs.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `idle-and-recovery`: extend "Idle container stop" to cover transport-side captain schedule entries.

## Impact

- `transport/monitors.py` — `_idle_monitor` only, ~5 lines
- `openspec/specs/idle-and-recovery/spec.md` — requirement text update
- Unit tests in `tests/unit/test_monitors.py`
