# Proposal: Reduce default Podman machine memory from 16 GB to 8 GB

## Problem

The ghostship install script provisions a dedicated Podman machine with `GA_MACHINE_MEMORY=16384` (16 GB) by default. This is excessive: ghostship agents are primarily I/O-bound (waiting on LLM API calls) rather than memory-heavy, and 8 GB comfortably supports 3 concurrent crew containers with room to spare. A 16 GB default causes unnecessary memory pressure on the host, particularly on machines with 16 GB unified memory total.

## Proposed Change

Lower the default value of `GA_MACHINE_MEMORY` from `16384` to `8192` (8 GB) across all locations where the default is defined or documented.

No new configuration keys are introduced. No behaviour changes other than the numeric default.

## Scope

Active source files with the 16384 default (or references to "16 GB" / "16384 MB"):

| File | Change |
|:-----|:-------|
| `bin/install.sh` | `GA_MACHINE_MEMORY:-16384` → `GA_MACHINE_MEMORY:-8192` |
| `bin/lib/podman_setup.py` | dataclass default `16384` → `8192`; fallback `"16384"` → `"8192"` |
| `bin/lib/install_main.py` | fallback `"16384"` → `"8192"` |
| `bin/lib/yaml_config.py` | default map entry `"16384"` → `"8192"` |
| `config/ghostship.yaml.example` | `memory_mb: 16384` → `memory_mb: 8192` |
| `docs/configuration.md` | default column `16384` → `8192`; prose description updated |

Archived OpenSpec specs that document the old defaults are left as-is — they are historical records of what was true when those changes landed.

## Non-Goals

- No change to `GA_MACHINE_CPUS` (stays 8) or `GA_MACHINE_DISK` (stays 100).
- No change to the `podman machine set` resize path in `docs/troubleshooting.md` (that example already uses 8192).
- No migration tooling — this is a default-only change; existing machines are not touched.
