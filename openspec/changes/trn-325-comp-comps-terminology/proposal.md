# Proposal

## Why

Ghostship will use `comp` and `comps` across tool interfaces, resources, APIs, configuration, persisted crew records, implementation, and documentation. Existing clients and records may still use `composition` and `compositions`, so those spellings remain compatibility aliases at input and data boundaries during the migration.

## What Changes

- Make `comp` the canonical `launch` argument and retain `composition` as an optional alias. Accept equal values when both are provided and reject conflicting values.
- Expose `transport://comps` as the canonical discovery resource and retain `transport://compositions` as an alias to the same content.
- Use `comp` in crew records, MCP and REST payloads, Radar, internal implementation names, examples, and documentation. Read legacy `composition` data and preserve it at compatibility boundaries during the rollback window.
- Use `comps` as the canonical registry key while accepting legacy `compositions`; reject conflicting values if both keys are present.
- Implement the reviewed compatibility matrix under this same TRN-325 ticket and OpenSpec change, with behavior specs, tests, documentation, and coordinated shared-skill updates.

## Capabilities

### Modified Capabilities

- `crew-lifecycle` — canonical launch argument, alias resolution, persisted crew field, and backward-compatible reads.
- `crew-governance` — comp terminology in launch and policy behavior.
- `crew-types` — reconcile the stale capability contract with actual comp registry and discovery behavior, including aliases.
- `mcp-server` — canonical crew payload field and MCP discovery terminology.
- `transport/crews-rest-api` — canonical `comp` response field and compatibility alias.
- `installation` — comp terminology in image discovery and resource behavior.
- `transport-test-coverage` — registry and alias error-path coverage for renamed internals.

## Impact

Implementation will cover `transport/tools.py`, registry and crew persistence, Radar and REST payloads, MCP resource registration, internal identifiers, installer examples, relevant OpenSpec specs, tests, docs, and shared Ghostship skills in the sibling executor repository. Existing comp identifiers, directory names, policy filenames, manifest schema, and environment variables remain unchanged. No alias-removal date is set in this change.
