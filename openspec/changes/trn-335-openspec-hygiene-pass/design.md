# Design

## Context

Captain order templates are Academy Markdown files resolved by the transport and delivered to Raven. A hygiene pass can run OpenSpec's CLI against a supplied repository while Raven coordinates independent reviewers and reports their findings.

The public template is `repo-hygiene-sweep`, with `sweepy` as its short alias. Its repository-wide maintenance scope distinguishes it from Indy's change-review lifecycle.

## Goals / Non-Goals

**Goals:** Perform one manually ordered repository-maintenance pass; use the target repository's own OpenSpec root/store; separate authoritative CLI status from reviewer judgments; include a broad privacy and sensitive-data sweep; and leave the target untouched.

**Non-Goals:** Replace Indy or perform its change-scoped code-quality and security review; change specs, sync or archive changes; or run on a recurring schedule.

## Decisions

- **Use a Captain order template for manual invocation.** This matches the existing Specky and Indy entry point. The template performs one bounded pass and uses the standard Captain completion mechanism to end its check-in, rather than creating an independent background schedule.
- **Resolve the target before running checks.** Run OpenSpec context/status from the supplied repository and honor its resolved root/store. If the root is absent or a declared store cannot be resolved, report the blocker. Do not initialize a store, register one as a side effect, or fall back to Ghostship's own store; those actions violate the read-only contract and risk inspecting the wrong project.
- **Keep CLI evidence separate from interpretation.** Raven runs strict validation and collects change/artifact/task status. Independent reviewers inspect specification content and contradictions, spec-related code risks, documentation coherence, and privacy/sensitive-data exposure. The privacy reviewer sweeps the whole target repository even when change-specific checks are selected. Raven waits for each report and preserves file paths, line references, status output, and uncertainty in the consolidated result.
- **Use the bundled verifier for apparent completion candidates.** When OpenSpec status and task progress make a selected change look ready for verification, invoke the required `openspec-verify-change` skill bundled by TRN-326 and include its advisory report. If invocation fails, stop and escalate an execution blocker rather than producing a partial hygiene report.
- **Separate repository hygiene from change review.** Hygiene catches accumulated repository-wide privacy and sensitive-data exposure and checks docs against specs and implementation. Indy remains the change-review workflow for correctness, quality, security, and privacy concerns in the change under review; the two orders run at different lifecycle points.
- **Protect sensitive evidence in reports.** Identify a finding by path, line, category, and a short redacted description; do not copy secret values or unnecessary personal data into the Admiral report.
- **Make the report advisory.** Mark candidates for verification/archive based on observable status, but do not assert that verification passed or archive changes. No files, specs, or work item statuses are modified.

## Risks / Trade-offs

- **Risk:** Static comparisons may produce false positives or miss runtime behavior. **Mitigation:** Label reviewer assessments separately from CLI validation, include evidence and confidence, and state when evidence is unavailable.
- **Risk:** Documentation review can drift into Indy territory. **Mitigation:** Limit it to coherence with the target repository's specs and implementation, excluding general documentation completeness.
- **Risk:** A broad privacy scan may expose the very data it finds in its report. **Mitigation:** Redact values and report only enough context to locate and remediate the finding.
