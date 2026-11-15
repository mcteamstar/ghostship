# Design

## Context

Ghostship currently exposes `composition` on the `launch` MCP tool and in crew payloads; the crew discovery resource is `transport://compositions`. Registry and persistence code also use the old terminology. This change makes `comp`/`comps` canonical throughout while preserving the old spellings only where existing clients or stored data need aliases.

## Goals / Non-Goals

**Goals:**
- Use `comp`/`comps` across interfaces, configuration, persisted records, implementation names, and documentation.
- Preserve `composition`/`compositions` aliases at compatibility boundaries and make alias precedence deterministic.
- Keep existing comp identifiers, directories, policy filenames, and manifest schema stable.

**Non-Goals:**
- Rename comp identifiers or directory paths, policy filenames, manifest keys, or environment variables.
- Set an alias removal date; that requires usage evidence and a separate decision.
- Keep implementation and documentation changes within this repository.

## Decisions

### Launch input alias resolution

`comp` is the canonical launch argument. `composition` remains an optional alias. Both inputs default to `None` so omission can be distinguished from explicit values; if both are omitted, apply the existing `spec-ops` default after alias resolution. When both are supplied, `comp` is authoritative; differing values log a warning and `comp` is used. Old spelling appears only in launch-boundary compatibility handling and documentation of that alias.

### Resource alias

Register `transport://comps` as the canonical resource and retain `transport://compositions` as an alias that returns identical content from the same implementation. The resource name and title use “comps.”

### API and persisted field compatibility

`comp` is canonical in internal crew objects, persisted records, MCP output, REST output, and Radar. During the rollback window, serialize both `comp` and `composition` with the same value. Readers accept records with only `composition`; if both fields differ, `comp` is authoritative and the mismatch is logged. MCP and REST responses expose both fields with equal values until a later removal decision.

### Registry key compatibility

The authored registry and loader use `comps` canonically and accept legacy `compositions`. If both keys are present with different values, `comps` wins and the loader logs a warning; if `comps` is not a list, a valid `compositions` list is used. If equal, accept them as one registry. Registry entry names and directories stay stable.

### Internal names and rollout scope

Rename internal Python symbols to `comp` terminology; confine legacy spellings to explicit normalization and serialization compatibility code. Update the installer example, product docs, OpenSpec requirements, and tests within this repository.

## Risks / Trade-offs

- [Strict clients reject additive response fields] → Confirm MCP/REST consumers and retain same-value aliases for the agreed compatibility window; update contracts and examples together.
- [Persisted records differ across versions] → Read legacy-only records, write both fields during rollback compatibility, treat `comp` as authoritative on mismatch, and cover this behavior with tests.
- [Some surfaces keep old terminology] → Track source, UI, docs, installer output, and specs as explicit implementation tasks; old spelling remains only where alias behavior requires it.

## Migration Plan

First author and validate behavior delta specs for the listed capabilities. Then implement in compatible layers: launch/resource aliases; registry and persisted data handling; MCP/REST output and Radar; internal symbol and documentation updates. Keep all old aliases active through the rollback window. The same TRN-325 ticket remains open until implementation is complete; do not archive after planning or discovery.

## Open Questions

No unresolved design questions block delta spec authoring. External client inventory remains necessary before selecting any future alias-removal date; this change retains the aliases and sets no removal date.
