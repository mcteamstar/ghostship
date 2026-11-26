# Spec Delta

## ADDED Requirements

### Requirement: ghostship-spawn dispatch supports a model override
`ghostship-spawn` SHALL accept an optional `--model <id>` after the persona name and include the validated model ID in that named task's spawn request. When omitted, the helper SHALL preserve the existing request payload without a `model` field.

#### Scenario: Dispatch with a model override
- **WHEN** an agent runs `ghostship-spawn banshee --model claude-opus-5` with task text on standard input
- **THEN** the helper creates a retained banshee task and sends `model: "claude-opus-5"` in the `/api/spawn` request body

#### Scenario: Dispatch without a model override
- **WHEN** an agent runs `ghostship-spawn ghost` with task text on standard input
- **THEN** the helper sends the existing dispatch payload without a `model` field

### Requirement: ghostship-spawn restricts and validates model overrides
The helper SHALL accept `--model` only for named-persona dispatch and SHALL reject `--model` with no following value, an empty value, or a malformed model ID before contacting the gateway. A valid ID SHALL be at most 500 characters and match `^[A-Za-z0-9][A-Za-z0-9._-]*$`.

#### Scenario: Invalid model is rejected
- **WHEN** an agent runs `ghostship-spawn banshee --model` without a value, or supplies an empty, malformed, or overlong model ID
- **THEN** the helper exits non-zero with its one-line usage error on standard error and makes no gateway request

#### Scenario: Model option on a non-dispatch operation is rejected
- **WHEN** an agent supplies `--model` with `--list`, `--status`, `--steer`, or `--continue`
- **THEN** the helper exits non-zero with its one-line usage error and makes no gateway request
