# Design

## Context

See proposal.md. Two enforcement points: `install.sh` (build time) and `transport/server.py` (runtime). Both already have the `GA_REQUIRE_API_KEY` check — this change promotes the default from `warn` to `error`.

## Goals

- Remote installs without `GA_API_KEY` abort at both install time and transport startup
- Local (loopback) installs unaffected
- `off` override works for proxy-protected deployments

## Non-Goals

- Changing how `GA_API_KEY` is delivered (Podman secret — already done in TRN-211)
- Removing the `warn` mode (can be done in a future cleanup)

## Decisions

### D1 — Two enforcement points are independent

`install.sh` checks after image builds, before `compose up` (i.e. before any containers start). `transport/server.py` checks at startup. Both use the same `GA_REQUIRE_API_KEY` env var. The transport check is a safety net in case the transport image is deployed without going through `install.sh` (e.g. manual `podman run`). No coordination needed between the two — they read the same setting independently.

### D2 — Loopback detection

At install time: check `HOST` value. The script default is `0.0.0.0` (non-loopback); to get a loopback install the operator must set `HOST=127.0.0.1` explicitly (via conf or flag). `127.0.0.1`, `::1`, and `localhost` are treated as loopback and skip the check; anything else (including the default `0.0.0.0`) is non-loopback.

At transport startup: check the `HOST` env var passed into the container. If `HOST` is unset or `127.0.0.1`/`::1`/`localhost`, skip the check.

### D3 — warn mode kept for backward compatibility

Operators who explicitly set `GA_REQUIRE_API_KEY=warn` in their conf get the old behaviour. Not documenting `warn` as supported going forward, but not removing it either. If `warn` is set and no key is present on non-loopback, log a warning and continue.
