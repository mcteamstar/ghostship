# Design

## Context

See proposal.md for motivation. Versions currently live in crew toolchain shell scripts, Containerfiles, installer configuration/defaults and transport/requirements.txt. Kiro CLI is inherited from the digest-pinned KiroCrew image; Codex CLI is inherited from its ACP adapter dependency. Node.js follows a major release stream, Python packages include ranges, and shared agent assets default to a moving branch. Existing GitHub Actions run tests and release gates, but no scheduled dependency report exists. Existing dependency-management requirements continue to govern Python provenance and pins.

## Goals / Non-Goals

**Goals:** Make every external input discoverable, distinguish configured versions from installed resolutions, and make overdue reviews and incompatible combinations visible.

**Non-Goals:** Scheduled jobs, GitHub Actions integration, automated reporting, automatic merging, deployment, live crew modification, independently pinning Codex CLI away from its adapter, or repairing the current model-selection issue as part of this maintenance change.

## Decisions

### Inventory and ownership

Add `config/dependencies.yaml` as maintenance metadata and `docs/dependencies.md` as the linked runbook. Keep existing executable declarations authoritative rather than moving all installers into a new version manager. Each record has a stable id, component/category, declaration locations and extractor, upstream source, version policy, review owner role (Ghostship maintainers initially), review date/outcome, compatibility notes and evidence link. Derived components explicitly reference their parent and record observed versions separately from declared constraints. Represent dynamic inputs honestly as streams/ranges/branches, with unknown installed resolution until inspected.

Initial coverage includes KiroCrew digest and bundled Kiro CLI; Codex ACP and bundled CLI; Claude ACP and Claude Code; OpenSpec CLI and generated skill compatibility; Node.js stream and setup-script checksum; transport/worker Python image; all direct Python runtime/test dependencies; crew cryptography; shared `.agents` source/ref; and externally fetched OS/package inputs. OS packages are tracked as a managed group with distro/update policy, not a manually duplicated package lock. Audit installer download paths for additional inputs during implementation.

Alternative: a Markdown-only list is simpler but drifts silently. A machine-readable registry permits manually invoked local drift checks while the runbook explains decisions. Avoid a second independent hard-coded version list by extracting current constraints from declarations.

### Read-only reports and drift detection

Provide a manually invoked local command printing a concise human-readable result: declared constraint, last verified installed version if recorded, upstream stable candidate, compatibility/review status, checked time and source. Separate newer from compatible: registry metadata alone cannot certify KiroCrew support. Adapters/CLIs and OpenSpec/skills are reviewed as coupled groups. A failed upstream lookup reports unknown/error, never up-to-date; one failure must not hide other results. Inventory completeness and stale declaration metadata are reported by the manual command. Upstream outages produce partial output and a nonzero exit status. No report retention or publishing infrastructure is required.

Use public registry/release metadata with bounded timeouts, pagination and explicit stable/prerelease policy. No crew authentication is needed. Add fixture-based tests for version policies, derived dependencies, lookup failures, drift and incompatible groups. Avoid introducing a new dependency-management service initially; a small manually invoked script covers custom shell pins and inherited components that generic update bots miss.

### Cadence and review visibility

Checks run only when a maintainer invokes the documented local command. There is no scheduled workflow, workflow_dispatch wrapper, automatic publishing, artifact retention or notification. Link the inventory, runbook and command from README.

Maintainers review monthly and before each release, recording the date, compatible candidate or explicit deferral reason, evidence and next review. Check security advisories and upstream compatibility warnings sooner when discovered; this is not continuous vulnerability monitoring. Review reports explicitly flag entries older than 30 days and missing verification. Latest-compatible and latest-available are distinct; not every available update should be applied.

### Upgrade acceptance

A dependency upgrade changes authoritative declarations and review metadata in the same reviewed change. Preserve exact pins/digests where currently used. Validate adapter/CLI pairs with KiroCrew's supported range, login compatibility, model discovery and a minimal fresh-crew turn that records the actual model. Validate Kiro DB seed migrations when changing KiroCrew, OpenSpec skills when changing OpenSpec, Node setup checksums when changing the fetched script, and affected transport tests for Python changes. Record built component versions; a source bump alone is not installed verification. Rebuild cache behavior and new-crew adoption must be checked. Deployment remains explicitly approved; rollback restores prior declarations and images, retaining user credentials/workspaces.

## Risks / Trade-offs

- Registry availability or metadata format changes → bounded lookups, fixtures and visible partial failures.
- Inventory becomes another stale document → declaration extraction, manual drift checks and dated maintainer reviews.
- Upstream latest is incompatible → report candidates separately and require paired integration evidence.
- Inherited package versions are not inferable from a pin alone → mark unknown until build/crew evidence exists; never equate a constraint with an installed version.
- Manual reviews can be missed → README/runbook entry point, dated reviews and release checklists; no background monitoring or automatic ticket delivery.

## Migration Plan

Inventory existing declarations without upgrading them. Run the offline checker and a manual upstream report, document initial review findings and carry known Codex mismatch as an action item. Integrate the documented manual command and release checklist after review. Rollback removes maintenance tooling/metadata only; runtime behavior is unaffected. Applying any dependency upgrades is separate work with the normal deployment approval process.
