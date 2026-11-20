# Design

## Context

The Captain order catalog is discovered from Markdown files under `academy/orders/`. The standalone privacy template and aliases are supplied by `privacy.md`; privacy review is already included in `independent-review.md` and its existing capability spec.

## Goals / Non-Goals

**Goals:** Remove the standalone template and all user-facing references to it while preserving Indy privacy review.

**Non-Goals:** Change the privacy reviewer shard, its scan scope, or the independent-review workflow.

## Decisions

- Delete `academy/orders/privacy.md`. The transport dynamically indexes templates and aliases from Academy files, so removing this file removes the built-in order names without transport code changes.
- Update README and architecture documentation to list only the remaining built-in workflows.
- Confirm the built-in catalog is file-discovered and the independent-review order still defines its privacy reviewer.
- Retire the standalone `captain/privacy-probe` requirements through a REMOVED delta. Keep the independent-review spec unchanged because its privacy shard already specifies the retained behavior.

## Risks / Trade-offs

- **Risk:** Existing callers may still request a standalone privacy alias. **Mitigation:** This is the intended removal; the template resolver will report the name as unknown, and documentation directs operators to Indy.

## Migration Plan

Operators who previously selected `privacy`, `privacy-probe`, or `scrub` should select `independent-review` / `indy`; its existing Privacy shard remains enabled.
