# Design

## Context

The generated Compose configuration attaches Portal, Transport, and Radar to ga-portside; Transport and crew containers share ga-starboard. Runtime-created login containers use backend-specific prefixes, and the dashboard WebSocket proxy sends the gateway loopback Origin. Existing specs and docs describe an older topology.

## Goals / Non-Goals

**Goals:**
- Make the current generated topology the consistent steady-state contract.
- Keep ga-net references that describe actual migration logic.

**Non-Goals:**
- Change Compose network assignments or add a network.
- Expand Radar's authority over Transport or Caddy.

## Decisions

- Treat bin/lib/compose.py as the source for generated steady-state membership and runtime creation payloads as the source for ephemeral membership; list every supported login-container prefix in the table.
- Edit only inaccurate steady-state references. Preserve code-backed legacy ga-net cleanup: install removes it only when empty, and uninstall attempts removal after Ghost Academy containers are removed. Remove unsupported Transport-startup crew migration and dashboard hostname-Origin requirements.
- Validate static and ephemeral topology against source and focused tests, and align the dashboard WebSocket Origin requirement with transport/server.py.

## Risks / Trade-offs

- [A broad search-and-replace removes valid migration guidance] → Review every ga-net occurrence in context and preserve migration-specific references.
- [The table omits backend login flows] → Check the per-backend login prefixes and creation payloads.
- [Copied dashboard-proxy requirements retain stale behavior] → Compare Origin and config.local.json claims against the current proxy code.
- [Specs continue to disagree across capabilities] → Cross-check the Radar, network-split, installation, and crew-lifecycle specs together.
