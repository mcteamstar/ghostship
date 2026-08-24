## ADDED Requirements

### Requirement: Raven self-coordination dispatch-intent mail convention
The system SHALL establish a Raven self-coordination mail convention whereby Raven writes a tokenized dispatch-intent to its own mailbox (`raven@localhost`) before each persona dispatch and records the gateway-assigned task ID immediately afterward, providing a durable coordination signal across check-ins.

Each pre-spawn dispatch-intent message SHALL:
- Be addressed `To: raven@localhost` (generic form, since all Raven check-ins share the persistent session's mailbox)
- Use the subject format `dispatching <persona> <intent_id>`, where `<intent_id>` is a unique local token in the form `intent-<uuid>` generated before the spawn call; the gateway's real task ID is not known until the call returns
- Be written BEFORE the `/api/spawn` call, so the mailbox records intent before the async spawn-list state can lag
- Include `From: raven+<raven_task_id>@localhost` using the Raven check-in's own derived task ID
- Correspond to a worker task description beginning with `SDD dispatch <change> <persona> <intent_id>`

After a successful spawn, Raven SHALL write a confirmation message addressed to `raven@localhost` with subject `dispatching <persona> <spawn_task_id>`, where `<spawn_task_id>` is the ID returned by `/api/spawn`, and SHALL link the local intent token in the body. Raven SHALL not invent the gateway ID before the call.

Subsequent Raven check-ins SHALL scan `raven@localhost` for pending and confirmed dispatch-intents when determining whether a persona is already in flight. A pending intent SHALL block through one full subsequent confirmation check; it becomes stale only when no task carries its token and no matching worker is in flight. A confirmed intent becomes stale when its task is shown as finished or absent from `spawn list`. A post-write election SHALL allow only the oldest pending marker for a persona to proceed when check-ins overlap.

#### Scenario: Raven writes a tokenized intent before spawning Ghost
- **WHEN** Raven decides to dispatch Ghost for implementation and confirms all three layered signals are clear
- **THEN** Raven generates `intent-abc123`, prefixes the task description with `SDD dispatch <change> ghost intent-abc123`, writes `dispatching ghost intent-abc123` to `raven@localhost`, and only then calls `/api/spawn`

#### Scenario: Raven records the gateway-assigned task ID
- **WHEN** the spawn call returns task ID `abc123`
- **THEN** Raven writes a second message with subject `dispatching ghost abc123` and links it to the pre-spawn intent in the body

#### Scenario: Raven finds an existing pending dispatch-intent on the next tick
- **WHEN** a subsequent Raven check-in scans `raven@localhost` and finds `dispatching ghost intent-abc123` with no completed confirmation check
- **THEN** Raven treats Ghost as already dispatched and holds, even if `kirocrew spawn list` shows no `agent: ghost` entry due to async population lag

#### Scenario: Overlapping check-ins elect one intent
- **WHEN** two Raven check-ins write pending intents for Ghost before either has spawned
- **THEN** only the oldest pending marker by Maildir arrival/`Date` (then `Message-ID` for a tie) proceeds to `/api/spawn`, and the other check-in holds

#### Scenario: Pending intent whose spawn failed is stale after confirmation
- **WHEN** a subsequent check-in has confirmed that `intent-abc123` has no matching task description and no matching worker in flight
- **THEN** Raven treats the pending intent as stale and may retry if the standing order still requires Ghost

#### Scenario: Confirmed dispatch-intent with completed task is stale
- **WHEN** a Raven check-in finds `dispatching ghost abc123` as a confirmed intent AND `kirocrew spawn list` shows task `abc123` as completed or the task no longer appears
- **THEN** Raven treats that confirmed intent as stale/resolved and does not hold on its account — the persona may be dispatched again if orders require it
