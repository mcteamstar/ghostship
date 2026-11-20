# Tasks

## 1. Establish a baseline and metadata convention

- [x] 1.1 Run `openspec validate --all --strict --report findings --json` and save a dated, sanitized summary by category; verify totals match the command output. (Baseline recorded in proposal.md on 2026-11-20.)
- [x] 1.2 Update tracked OpenSpec workflow guidance and change metadata to use the v2-recognized extension form for Plane identifiers; verify each remains mapped to its TRN work item and no unknown-key warning remains.

## 2. Resolve findings in reviewable batches

- [x] 2.1 Replace placeholder Purpose sections with concise capability purposes; verify affected specs pass Purpose validation.
- [x] 2.2 Review overlong requirement descriptions and split multi-behavior requirements into focused requirements and scenarios without changing behavior; validate each batch and compare scenarios before and after.
- [x] 2.3 Rewrite non-normative requirement language as SHALL/MUST only where intended behavior is clear; verify each changed requirement against scenarios and source evidence.

## 3. Verify the baseline

- [x] 3.1 Re-run strict validation, compare category counts with the baseline, and document intentional remaining exceptions; verify no unexplained regression remains. (Final: 85/87 items pass; two intentional overlong contracts are documented in proposal.md.)
