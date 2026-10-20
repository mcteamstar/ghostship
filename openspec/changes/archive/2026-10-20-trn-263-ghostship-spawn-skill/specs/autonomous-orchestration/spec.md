## ADDED Requirements

### Requirement: Raven performs gateway operations through the ghostship-spawn skill
Every Raven prompt source SHALL instruct Raven to dispatch named personas, read task detail, steer running tasks and continue finished tasks with the `ghostship-spawn` command (see `persona-dispatch`), and SHALL NOT describe a hand-built gateway REST call. Those sources are the `raven.json` persona prompt, the Captain check-in orientation injected by the transport, and every built-in order template. None of them SHALL reference `.local_secret`, `X-Internal-Secret`, `X-Session-Key`, the dashboard cookie file, or a `curl` data-file argument (`-d @`, `--data @`, `--data-binary @`).

Raven SHALL keep the task text it passes to `ghostship-spawn` free of literal command lines that upload files or pipe downloads to a shell, describing such steps in words instead, and SHALL keep each brief well under 20 KiB, because the brief is part of the command the crew's tool gate scans. If `ghostship-spawn` is not available in the crew, Raven SHALL report that to the Admiral and hold rather than calling the gateway another way.

Raven SHALL treat a refused tool call on a gateway operation as a crew gate block, not a human decision. It SHALL report which operation was refused and hold, without asking for approval and without quoting the refused command line into mail.

#### Scenario: All prompt sources agree
- **WHEN** a Captain check-in is dispatched, combining the persona prompt, the check-in orientation and a resolved order template
- **THEN** every source tells Raven to use `ghostship-spawn` for gateway operations, and none describes an alternative authentication method or a hand-built `curl` call

#### Scenario: Template dispatch step uses the skill
- **WHEN** the `spec-driven-development` or `independent-review` template reaches a dispatch step
- **THEN** it tells Raven to dispatch with `ghostship-spawn <persona>` after writing the pending intent marker, and to record the gateway response's `id` field as the task ID in the confirmation marker

#### Scenario: Claude-backend Raven dispatches without a refusal
- **WHEN** Raven on a claude-backend crew dispatches a persona during a check-in
- **THEN** the dispatch is not refused by the crew's tool gate because of how the call was written

#### Scenario: Helper missing
- **WHEN** a check-in needs a gateway operation and `ghostship-spawn` is not available in the crew
- **THEN** Raven mails the Admiral that the skill is missing and holds, and does not build a `curl` call to the gateway

#### Scenario: A refusal is reported, not escalated as an approval request
- **WHEN** a `ghostship-spawn` call is refused by the tool gate
- **THEN** Raven mails the Admiral which operation was refused and holds, without retrying in the same cycle, without offering an "approve" option, and without quoting the command line

## REMOVED Requirements

### Requirement: Raven persona prompt uses cookie-only auth for spawn calls
**Reason**: Raven's prompts no longer describe how to build the gateway call. Cookie-only authentication now lives inside the `ghostship-spawn` helper (`persona-dispatch`). The requirement that the persona prompt and task text agree is now part of "Raven performs gateway operations through the ghostship-spawn skill", which also covers the order templates that previously contradicted it.
**Migration**: None for operators. Relaunch crews to pick up the skill and the updated prompts.
