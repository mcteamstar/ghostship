# Proposal

## Why

The transport can pin a model when it starts a crew task, but agents inside a crew cannot pass that choice through `ghostship-spawn`. Raven therefore cannot reliably honor a standing order that asks it to start reviewer or worker tasks on a specific model.

## What Changes

- Add an optional `--model <id>` argument to named-persona dispatch through `ghostship-spawn` and include it in the gateway spawn payload when supplied.
- Reject empty or malformed model IDs using the same format and length bounds as transport model validation. Keep the option unavailable to list, status, steer, and continue operations.
- Preserve existing dispatch behavior when `--model` is omitted.
- Document the option in the helper skill and Raven's gateway orientation, and cover parsing and payload behavior in unit tests.
- Leave the optional separate model field for `captain(action="order")` out of scope.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-orchestration/dispatch`: Extend the in-crew helper's named dispatch contract with an optional validated model override.
- `academy/agent-personas`: Teach Raven to pass an explicitly requested model through the helper when dispatching a named persona.

## Impact

Changes affect `academy/skills/ghostship-spawn/scripts/ghostship-spawn`, its `SKILL.md`, Raven's orientation in `academy/agents/raven.json` and `transport/captain.py`, and the helper and prompt consistency tests. The transport already validates and forwards model overrides; the helper will match its existing model-name bounds. The crew gateway API and Captain order schema remain unchanged.
