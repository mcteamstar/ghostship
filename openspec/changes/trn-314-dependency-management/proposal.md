# Proposal

## Why

Ghostship reviews KiroCrew on cadence, but independently installed adapters, CLIs and build dependencies have no equally visible maintenance process. An old Codex adapter silently limited the advertised model catalogue; rebuilding the image preserved the obsolete pin.

## What Changes

- Publish a linked dependency inventory covering KiroCrew and bundled Kiro CLI, Codex and Claude adapters/CLIs, OpenSpec and matching skills, Node.js, Python images, Python dependencies, shared agent assets and other externally fetched build inputs.
- Record authoritative declarations, direct versus bundled versions, compatibility constraints, ownership, last review and verification evidence.
- Add a manually invoked, read-only dependency check command with explicit unknown/failure results.
- Check inventory/declaration drift through the manual command and document a monthly human review plus a pre-release compatibility review. Security advisories and upstream incompatibility warnings trigger earlier review.
- Define compatibility tests, rebuild and fresh-crew checks, rollback and approval requirements for upgrades. Track immediate Codex/model repairs separately.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `dependency-management`: Extend existing Python provenance/pinning policy with repository-wide inventory, review reporting, cadence and upgrade verification requirements.

## Impact

New maintenance inventory, runbook, manual check command and README links. No scheduled jobs, GitHub Actions integration or automated reporting. Existing build/version declarations remain authoritative. No automatic upgrades, deployments or changes to running crews are introduced by the review process.
