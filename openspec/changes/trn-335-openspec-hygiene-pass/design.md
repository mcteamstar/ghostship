# Design

## Context

Captain order templates are Academy Markdown files resolved by the transport and delivered to Raven. A hygiene pass can run OpenSpec's CLI against a supplied repository while Raven coordinates independent reviewers and reports their findings.

## Goals / Non-Goals

**Goals:** Perform one manually ordered pass; use the target repository's own OpenSpec root/store; separate authoritative CLI status from reviewer judgments; and leave the target untouched.

**Non-Goals:** Replace Indy, perform general code-quality/security/privacy review, change specs, sync or archive changes, or run on a recurring schedule.

## Decisions

- **Use a Captain order template for manual invocation.** This matches the existing Specky and Indy entry point. The template performs one bounded pass and uses the standard Captain completion mechanism to end its check-in, rather than creating an independent background schedule.
- **Resolve the target before running checks.** Run OpenSpec context/status from the supplied repository and honor its resolved root/store. If the root is absent or a declared store cannot be resolved, report the blocker. Do not initialize a store, register one as a side effect, or fall back to Ghostship's own store; those actions violate the read-only contract and risk inspecting the wrong project.
- **Keep CLI evidence separate from interpretation.** Raven runs strict validation and collects change/artifact/task status. Independent reviewers inspect contradictions and spec-related code risks, while Wraith checks documentation against the relevant specs and implementation. Raven waits for each report and preserves file paths, line references, status output, and uncertainty in the consolidated result.
- **Keep findings within the hygiene boundary.** Report likely bugs only when grounded in a mismatch with an OpenSpec contract. General correctness, code quality, security, and privacy remain Indy responsibilities.
- **Make the report advisory.** Mark candidates for verification/archive based on observable status, but do not assert that verification passed or archive changes. No files, specs, or work item statuses are modified.

## Risks / Trade-offs

- **Risk:** Static comparisons may produce false positives or miss runtime behavior. **Mitigation:** Label reviewer assessments separately from CLI validation, include evidence and confidence, and state when evidence is unavailable.
- **Risk:** Documentation review can drift into Indy territory. **Mitigation:** Limit it to coherence with the target repository's specs and implementation, excluding general documentation completeness and privacy scanning.

## Open Questions

- The public Captain template name and aliases remain intentionally undecided. Select them before implementing the catalog entry; this does not change the analysis contract or scope.
