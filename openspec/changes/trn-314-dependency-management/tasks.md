# Tasks

## 1. Inventory and maintenance guide

- [x] 1.1 Audit Containerfiles, toolchain scripts, installer download paths, Python requirements and shared asset refs; create config/dependencies.yaml with direct, inherited and grouped OS inputs, authoritative locations, owner and review fields; verify every discovered input is represented without claiming unobserved installed versions.
- [x] 1.2 Add docs/dependencies.md and README links describing version sources, monthly/pre-release reviews, urgent compatibility/security triggers, deferrals and upgrade/rollback checks; verify all links and commands resolve and record the known Codex adapter mismatch as an initial finding.
- [x] 1.3 Implement offline inventory/declaration validation in the manual command; verify fixtures catch missing inputs, stale declarations, broken derived links and distinguish branches/ranges from installed versions.

## 2. Manual dependency checks

- [x] 2.1 Implement a documented manual check command with concise terminal output, bounded upstream lookups, stable/prerelease policies, review age and compatibility status; verify fixtures cover npm, PyPI, image/release sources, derived versions, partial failures and available-versus-compatible candidates.
- [x] 2.2 Run an initial manual upstream check and update review outcomes/evidence with next-review dates or explicit unknowns; verify all components receive a result and document any lookup limitations rather than marking them current.

## 3. Release integration and acceptance

- [x] 3.1 Add the pre-release review checklist to the existing release process, covering adapter/CLI support and actual-model smoke tests, Kiro DB seed migration, OpenSpec/skills, Node checksums and affected Python tests; verify each upgrade category has a concrete acceptance check and rollback guidance.
- [x] 3.2 Exercise the documented local workflow end to end and run affected tests; preserve sample command output showing an update candidate, overdue review, unsupported/unknown compatibility and lookup failure, and verify no runtime configuration or dependency pin is changed by reporting.

## 4. Independent implementation review follow-up

- [x] 4.1 Correct candidate handling for yanked PyPI releases and successful lookups with no stable match; report prerelease-only results when requested, paginate registry/release sources within a fixed bound, and mark capped scans incomplete.
- [x] 4.2 Include recorded compatibility evidence in check output, reject malformed inventory metadata with a clear validation error, and update the example output and regression coverage.
