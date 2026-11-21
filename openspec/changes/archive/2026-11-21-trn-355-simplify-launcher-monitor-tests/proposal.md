## Why

Launcher startup-election tests use timing sleeps and overlapping fixtures. Monitor tests drive an entire infinite loop by raising StopIteration from sleep.

## What Changes

Use deterministic launcher tests and callable single ticks for the schedule, idle, and Captain monitors.

## Capabilities

No behavior contract changes.

## Impact

Launcher and monitor tests plus internal monitor loop structure. Runtime contracts and public tool surfaces stay compatible.
