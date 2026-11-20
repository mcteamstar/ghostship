# Proposal

## Why

OpenSpec repositories accumulate stale changes, incomplete artifacts, contradictions, and drift between specs, code, and documentation. A repeatable read-only hygiene pass will help clean up a repository once and keep its OpenSpec state coherent over time.

## What Changes

- Add a manually invoked, read-only Captain workflow for a whole repository or a selected set of OpenSpec changes, including foreign codebases.
- Add the Captain template `repo-hygiene-sweep` with the short alias `sweepy`.
- Resolve and use the target repository's own OpenSpec root/store; never fall back to Ghostship's store or initialize a missing store.
- Run strict OpenSpec validation and inspect change status, artifact/task completeness, contradictions, stale or missing specs, and relevant code/documentation drift.
- For changes that appear ready for verification, invoke the required bundled `openspec-verify-change` skill and include its advisory findings; TRN-326 supplies that skill.
- Run a broad repository-wide privacy and sensitive-data sweep, even when change-specific checks are selected; report findings with safe, redacted evidence and recommended remediation.
- Fan out independent, bounded reviews and consolidate findings with paths, status evidence, confidence, and recommended remediation.
- Report which changes appear ready for verification/archive and which appear stale or out of date, without editing, syncing, archiving, scheduling recurring work, or accessing deployed environments.
- Keep Indy as the change-review workflow for code correctness, quality, security, documentation, and privacy at that lifecycle point. Hygiene performs a separate broad repository-maintenance sweep for privacy and sensitive-data exposure, plus documentation coherence with OpenSpec and implementation.

## Capabilities

### New Capabilities

- `captain/openspec-hygiene`: A read-only Captain workflow for validating and maintaining OpenSpec hygiene across local or foreign repositories.

### Modified Capabilities

None.

## Impact

Adds an Academy Captain order template and updates Captain template documentation and OpenSpec requirements. It uses the bundled OpenSpec v2 CLI and the target repository's own store; no deployed service or external environment is accessed.
