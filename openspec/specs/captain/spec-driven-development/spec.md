# captain/spec-driven-development Specification

## Purpose

Defines Captain's built-in spec-driven development standing order.

## Requirements

### Requirement: The built-in SDD template preserves the OpenSpec lifecycle discipline

The `sdd` template SHALL direct Raven through planning, implementation, independent review, and archive, escalate after one unsuccessful fix/re-review cycle, and verify archive state directly.

#### Scenario: Planning incomplete
- **WHEN** a check-in following the `"sdd"` template finds the named change's proposal, design, specs, or tasks artifact not yet done
- **THEN** Raven dispatches Spectre to continue proposing or updating the change, and takes no other dispatching action that check-in

#### Scenario: Unchecked tasks
- **WHEN** a check-in following the `"sdd"` template finds planning complete and at least one unchecked item in `tasks.md`
- **THEN** Raven dispatches Ghost to implement the change's remaining tasks

#### Scenario: Implementation complete, no review yet
- **WHEN** a check-in following the `"sdd"` template finds every `tasks.md` item checked and no review recorded since the last implementation dispatch
- **THEN** Raven dispatches Banshee to independently review the implementation

#### Scenario: Review clean
- **WHEN** Banshee's review reports no unresolved findings
- **THEN** Raven dispatches Reaper to sync specs and archive the change, and confirms archival by reading OpenSpec state on a later check-in rather than assuming it from the dispatch alone

#### Scenario: Review still finds unresolved issues after one fix cycle
- **WHEN** Banshee's review reports unresolved findings, and this is not the first review cycle for the current implementation
- **THEN** Raven escalates to the Admiral rather than dispatching another review or fix cycle
