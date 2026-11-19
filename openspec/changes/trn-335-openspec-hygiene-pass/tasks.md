# Tasks

## 1. Captain order and target resolution

- [ ] 1.1 Settle the public Captain template name and aliases before implementation; verify the chosen names do not collide with existing built-in or operator templates.
- [ ] 1.2 Add the one-pass Academy order and independent reviewer briefs; verify the order self-cancels after reporting and creates no recurring hygiene run.
- [ ] 1.3 Resolve OpenSpec from the supplied repository and honor its own root/store; add coverage proving missing or unresolved roots cause a blocker without initialization, registration, or fallback.

## 2. Validation and lifecycle reporting

- [ ] 2.1 Run strict OpenSpec validation for whole-repository and selected-change scopes; add coverage for validation errors and evidence in the report.
- [ ] 2.2 Collect artifact and task status for selected changes; add coverage that incomplete, stale, and verification/archive-candidate states are reported without claiming completion or changing state.
- [ ] 2.3 Invoke the bundled `openspec-verify-change` skill for changes that appear ready for verification; verify its advisory result is reported and unavailable skill evidence is marked not verified.

## 3. Independent cross-checks and reporting

- [ ] 3.1 Fan out separate spec/code consistency and documentation-coherence reviews; add coverage that each reviewer receives only its assigned scope and reports evidence paths and uncertainty.
- [ ] 3.2 Consolidate CLI results and reviewer findings into one Admiral report; add coverage for confirmed versus suspected findings and verify the workflow performs no edits, sync, archive, recurring schedule, or deployed-environment access.
- [ ] 3.3 Document when to use the hygiene order versus Indy and verify the docs describe its read-only OpenSpec scope and name consistently.

## Workflow follow-up

- Archive the change after implementation review and sync the delta spec into the main specs.
