## Purpose

Defines the in-crew `ghostship-spawn` helper that agents use to dispatch, inspect, steer and continue named persona tasks on their own crew gateway. It gives every agent the same fixed, gate-safe command for those operations, so no agent has to assemble gateway REST calls or handle the gateway credential itself.

## ADDED Requirements

### Requirement: ghostship-spawn covers the gateway operations the kirocrew CLI does not
Every crew whose manifest selects the `ghostship-spawn` skill SHALL provide a `ghostship-spawn` command that agents can run from their shell, with these forms:

- `ghostship-spawn <persona>` dispatches a new retained task to the named persona, with the task text read from standard input; its request sets `keep: true` so the task remains available for later status, steering or continuation.
- `ghostship-spawn --status <task_id>` returns that task's detail.
- `ghostship-spawn --steer <task_id>` redirects a running task, with the message read from standard input.
- `ghostship-spawn --continue <task_id>` resumes a finished task, with the task text read from standard input.

Each form SHALL call the crew's own gateway and write the gateway's JSON response to standard output.

`ghostship-spawn` SHALL send requests only to the crew's own gateway on the loopback interface, at fixed `/api/spawn` paths. It SHALL NOT accept a URL, host, port or path from its arguments, standard input or environment, so it cannot send data to any other destination.

#### Scenario: Dispatch a named persona
- **WHEN** an agent runs `ghostship-spawn ghost` with the task text on standard input
- **THEN** a retained ghost task is created on the crew's gateway with exactly that task text, and standard output carries the gateway's JSON response, including the new task's `id` field

#### Scenario: Steer and continue use the same command
- **WHEN** an agent runs `ghostship-spawn --steer <task_id>` or `ghostship-spawn --continue <task_id>` with text on standard input
- **THEN** the running task is redirected, or the finished task is resumed, with that text, and the gateway's JSON response is written to standard output

#### Scenario: Destination cannot be redirected
- **WHEN** `ghostship-spawn` is run with any arguments, input or environment
- **THEN** every request it makes goes to the crew's own loopback gateway at an `/api/spawn` path, and to nowhere else

#### Scenario: Status lookup
- **WHEN** an agent runs `ghostship-spawn --status <task_id>`
- **THEN** standard output carries that task's detail as returned by the gateway

### Requirement: ghostship-spawn handles gateway authentication itself
`ghostship-spawn` SHALL authenticate with the crew's dashboard session cookie and the gateway's allowed origin, read inside the helper. It SHALL NOT send `X-Internal-Secret` or `X-Session-Key`, SHALL NOT read `.local_secret`, and SHALL NOT write the cookie value to standard output, standard error or any file.

#### Scenario: No credential in the agent's command
- **WHEN** an agent dispatches a persona with `ghostship-spawn`
- **THEN** the command the agent runs contains no cookie value, secret file path, `curl` invocation or `@file` data argument

#### Scenario: Cookie never echoed
- **WHEN** `ghostship-spawn` succeeds or fails for any reason
- **THEN** neither its output nor its error output contains the cookie value

### Requirement: ghostship-spawn reports failures plainly
`ghostship-spawn` SHALL exit non-zero, with a one-line error on standard error, when its arguments are invalid, the task text is empty, the cookie cannot be read, or the gateway returns a non-2xx response. For a gateway error it SHALL include the HTTP status and the response body.

#### Scenario: Gateway refuses the request
- **WHEN** the gateway returns a non-2xx status to a `ghostship-spawn` call
- **THEN** the command exits non-zero and its error output names the HTTP status and includes the response body, without the cookie

#### Scenario: Empty task text
- **WHEN** `ghostship-spawn <persona>` is run with empty standard input
- **THEN** it exits non-zero without calling the gateway
