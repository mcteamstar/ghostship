# Design

## Context

See proposal.md. Install scripts choose the Podman machine name and storage root from configuration and environment defaults. Troubleshooting guidance must describe those paths while remaining useful when operators override them.

## Goals / Non-Goals

**Goals:**
- Make Podman commands use the configured machine name and storage location.
- Ensure version and image-count claims are backed by current code.

**Non-Goals:**
- Change the installer, Podman machine defaults, or supported minimum version.

## Decisions

- Treat installer constants, config loading, and image build steps as the source of truth.
- Prefer GA_MACHINE_NAME and XDG_DATA_HOME in examples instead of hard-coded clone-specific paths.
- Keep troubleshooting commands narrowly scoped to the dedicated Ghostship instance.

## Risks / Trade-offs

- [A variable-based command is less copy-and-paste friendly] → Show a concrete default expansion only where it matches current defaults.
- [Version guidance diverges from a runtime check] → Confirm whether a checker exists and distinguish documented support from an enforced minimum.
