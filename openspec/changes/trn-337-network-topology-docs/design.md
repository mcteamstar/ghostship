# Design

## Context

The generated Compose configuration attaches Portal, Transport, and Radar to ga-portside; Transport and crew containers share ga-starboard. Existing specs and docs describe an older topology.

## Goals / Non-Goals

**Goals:**
- Make the current generated topology the consistent steady-state contract.
- Keep ga-net references that describe actual migration logic.

**Non-Goals:**
- Change Compose network assignments or add a network.
- Expand Radar's authority over Transport or Caddy.

## Decisions

- Treat bin/lib/compose.py as the source for generated steady-state membership and update relevant specs and docs to match.
- Edit only inaccurate steady-state references. Migration instructions that describe old ga-net containers remain if they match current migration code.
- Validate the generated topology against the spec table by inspecting Compose-generation code and its focused tests.

## Risks / Trade-offs

- [A broad search-and-replace removes valid migration guidance] → Review every ga-net occurrence in context and preserve migration-specific references.
- [Specs continue to disagree across capabilities] → Cross-check the Radar, network-split, installation, and crew-lifecycle specs together.
