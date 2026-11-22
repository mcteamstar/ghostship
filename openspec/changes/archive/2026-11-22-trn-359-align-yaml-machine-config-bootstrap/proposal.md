# Proposal

## Why

The installer provisions the dedicated Podman machine before Python resolves the effective YAML configuration. A machine name or resource setting in the YAML can therefore be ignored during provisioning, leaving the runtime machine inconsistent with the configuration Ghostship reports and uses later.

## What Changes

- Resolve the effective installation configuration before provisioning Podman.
- Use the resolved dedicated-machine name and resource limits for first-time provisioning and existing-machine selection.
- Keep explicit config-file precedence and the documented rule that ambient shell variables are not configuration inputs.
- Clarify configuration precedence and the XDG path environment inputs in the install documentation.
- Add regression coverage for YAML-driven provisioning, including the explicit `--config` path.

## Capabilities

- `installation`
- `testing/installation`

## Impact

Installer bootstrap order, Podman setup inputs, installation tests, and configuration documentation change. No runtime API or persisted crew data changes are intended.
