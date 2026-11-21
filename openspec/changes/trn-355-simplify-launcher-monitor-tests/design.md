## Context

Launcher startup-election tests use timing sleeps and overlapping fixtures. Monitor tests drive an entire infinite loop by raising StopIteration from sleep.

## Decisions

Reuse FakePodmanClient and a fresh launcher. Synchronize leader and waiter with bounded events, checking one startup cycle and outcomes for each caller. Extract one tick from each monitor loop and test it with a controlled clock, registry, and gateway. Preserve loop cadence, lock boundaries, and exception handling.

The schedule and idle loops sleep before the first tick. Captain computes its next wakeup from due entries and sleeps after the tick. Give a Captain tick a next-wakeup result and keep sleep in the loop. Preserve the idle monitor's skip on unavailable Podman and its activity recheck before stopping a crew. Keep fixture and clock patches local so this can proceed alongside TRN-354.

## Risks / Trade-offs

A loop extraction can change which failures terminate or skip a tick. Preserve exception scope and verify scheduling before and after each outcome.
