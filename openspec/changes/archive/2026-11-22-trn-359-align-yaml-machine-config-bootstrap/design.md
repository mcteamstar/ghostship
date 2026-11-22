# Design

## Context

See proposal.md for motivation. `bin/install.sh` currently provisions Podman before invoking `bin/lib/install_main.py`; the Python entry point resolves the layered YAML configuration only after that provisioning. The Python path already owns YAML resolution, `PodmanConfig`, platform setup, and data-directory calculation.

## Goals / Non-Goals

**Goals:**
- Make the resolved YAML configuration the single source for dedicated Podman machine selection and resource limits.
- Keep client-only installation out of Podman provisioning.
- Preserve the existing repository, XDG, explicit-config, and CLI precedence rules.
- Document that XDG environment variables choose config/data/runtime paths while machine settings themselves come from the resolved YAML layers.

**Non-Goals:**
- Add machine-specific CLI flags or make ambient environment variables configuration inputs.
- Change Podman machine lifecycle or the platform-specific setup implementation.

## Decisions

- Move Podman provisioning and socket/data-directory resolution into `install_main.py` after `_resolve_config` and config-to-environment population. The existing Python setup modules can then consume the same resolved values as compose generation.
- Remove the shim's pre-Python provisioning and its `PODMAN_SOCK`/`DATA_DIR` handoff. Keep prerequisite checks and the `--client-only` early exit; do not maintain a second YAML resolver in Bash.
- Build `PodmanConfig` from resolved `GA_MACHINE_*` settings, then derive and export the socket and data directory from the selected machine. This avoids a pre-resolved socket causing the Python installer to skip setup for the selected YAML machine.
- Clarify in `docs/configuration.md` that machine settings are resolved before provisioning and that the XDG directory variables select file locations rather than overriding YAML machine values.
- Alternative considered: teach the Bash shim to parse/merge YAML. Rejected because it duplicates precedence logic and would continue to risk drift from runtime configuration.

## Risks / Trade-offs

- [Provisioning starts later in the installer process] → The same prerequisite checks remain in the shim, and setup still occurs before image build, compose generation, or container startup.
- [Inherited internal socket/data variables could bypass setup] → The normal installer path derives these values after resolving config and does not seed them in the shim; regression tests cover the resolved machine inputs.

## Migration Plan

No data migration is required. Existing dedicated machines are selected by the effective configured name and retain their current resources; new machines use the resolved resource limits. Rollback is reverting the installer flow change.
