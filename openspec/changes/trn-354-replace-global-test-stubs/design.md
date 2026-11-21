## Context

Unit collection substitutes HTTP and ASGI modules process-wide. Gateway integration tests then lose real MockTransport when both suites are collected together.

## Decisions

Use real HTTP exceptions and responses and real ASGI requests or an in-process client. Replace global module substitutions with local fake transports, temporary registry paths or fixture-scoped persistence, and existing fake Podman clients. Keep network hermetic with an explicit test guard. Preserve separate live Podman and Corsair suites.

Treat collection as part of the isolation boundary. Remove per-file sys.modules fallbacks as well as the central stubs. Set temporary data paths before importing modules that initialize file signing or registry state. Guard outbound HTTP and Podman access at test boundaries while allowing in-process ASGI and mock transports. Restore fixture-level patches after each test.

## Risks / Trade-offs

A broad stub removal can expose import-time singleton state and accidental I/O. Migrate one dependency at a time and exercise mixed collection in both orders.
