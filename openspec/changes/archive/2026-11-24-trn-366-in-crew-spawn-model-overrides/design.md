# Design

## Context

See proposal.md for the motivation. The helper is a standalone script shipped inside crew images. Transport model validation currently allows IDs up to 500 characters matching `^[A-Za-z0-9][A-Za-z0-9._-]*$`. The helper's dispatch payload is assembled separately from transport calls.

## Goals / Non-Goals

**Goals:**
- Keep in-crew model selection aligned with the existing transport contract.
- Make the option available only when creating a named-persona task.
- Preserve current requests when no model is supplied.

**Non-Goals:**
- Add a model field to the Captain order API or persisted order format.
- Change gateway model resolution or validation.

## Decisions

- Extend the helper's argument parser to return an optional model for named dispatch. `main()` adds `model` to the existing payload only when the option is present; list, status, steer, and continue retain their current argument and payload paths. This keeps the change at the helper boundary and preserves the no-override payload.
- Mirror the transport's 500-character limit and model-name pattern in the standalone helper. Importing the transport validator would couple a crew-installed script to code that is not available inside a crew; relying only on gateway validation would not provide the helper's normal local argument error.
- Update the helper skill and Raven's gateway orientation so an explicit model instruction is translated into `--model <id>` on the dispatch command. Keep the orientation text synchronized between `academy/agents/raven.json` and `transport/captain.py`, which injects it into Captain check-ins. The task text remains on standard input and credentials remain managed inside the helper.
- Add parser and request-payload cases to the existing helper unit tests. Cover omitted, valid, empty, malformed, overlong, and non-dispatch uses so the CLI boundary and transport format stay aligned.

## Risks / Trade-offs

- The duplicated model-name bounds could drift from transport validation. Keep the exact bounds in tests and review them alongside transport validation changes.
- Existing crews continue to use the helper from their current image until recreated with a rebuilt image; there is no persisted state migration.

## Migration Plan

Rebuild the crew image to ship the updated helper and recreate crews that need the option. Existing running crews retain the helper already installed in their image. Rollback requires recreating affected crews with the previous image; no persisted task or order data needs migration.
