## Why

Unit collection substitutes HTTP and ASGI modules process-wide. Gateway integration tests then lose real MockTransport when both suites are collected together.

## What Changes

Use installed runtime libraries and isolate external I/O at test boundaries.

## Capabilities

No behavior contract changes.

## Impact

Unit harness, unit tests and offline Python integration runner.
