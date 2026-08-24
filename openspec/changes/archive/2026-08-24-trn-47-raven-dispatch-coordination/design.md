## Context

See proposal.md — Why. Raven's check-in loop currently relies on the `agent` field from `kirocrew spawn list` to detect in-flight workers, but this field is populated asynchronously after dispatch. Rapid-fire check-ins after a long-running task can each see the field empty and duplicate-dispatch the same persona.

The delivered project stores standing orders in `academy/orders/sdd.md` and Raven's check-in behavior is shaped entirely by that template plus the STANDING_ORDERS steering file. The crew gateway generates a spawn ID inside `POST /api/spawn`; Raven cannot know that ID before making the call.

## Goals / Non-Goals

**Goals:**
- Eliminate duplicate persona dispatches caused by async agent-field population lag
- Provide a durable mailbox intent record before the spawn call, with an explicit handoff to the gateway-assigned task ID afterward
- Add a layered signal approach (mailbox → stable task-description marker → agent field) that degrades gracefully if any single signal fails
- Serialize overlapping intent attempts through a deterministic post-write election without adding transport infrastructure
- Encode the pattern in the SDD template so every Raven session applies it consistently

**Non-Goals:**
- Changing ghostship transport code or the spawn API itself
- Adding new MCP tools or infrastructure services
- Modifying how other personas (Ghost, Spectre, etc.) behave
- Changing the recurring check-in schedule or job mechanism

## Decisions

### Decision 1: Two-phase mailbox intent around the server-assigned ID

**Choice:** Before each spawn, Raven generates a unique local `intent_id` in the form `intent-<uuid>`, prefixes the worker task description with `SDD dispatch <change> <persona> <intent_id>`, and writes `dispatching <persona> <intent_id>` to `raven@localhost`. Only after this record exists and wins the pending-marker election does Raven call `POST /api/spawn`. The gateway response supplies the real `spawn_task_id`; Raven immediately writes a confirmation with subject `dispatching <persona> <spawn_task_id>` and links it to the local token in the body.

**Why over alternatives:**
- *Writing the real task ID before spawn:* impossible because the gateway creates that ID inside the request, and inventing one would make stale detection unable to identify the actual task.
- *Waiting for the spawn response before writing any mail:* recreates the async visibility window that caused duplicate dispatches.
- *Lock file approach:* a durable lock file risks stale locks if Raven's session crashes. Maildir delivery is atomic and append-only; the pending marker is recoverable through the same mailbox protocol.
- *Database/KV store:* would require new infrastructure. The mail system already exists and is the crew's established coordination primitive.

### Decision 2: Layered signals plus a stable task marker

**Choice:** Raven checks (1) pending or confirmed mailbox intents, (2) the `task` text in spawn-list entries for the exact change/persona/token marker, and (3) the asynchronous `agent` field. All three must be clear before creating a new pending intent. Every SDD worker task carries the marker so the secondary check is actionable even before the gateway's `agent` field is populated.

**Rationale:** The mailbox covers the window between intent-write and spawn-list population; task text covers a lost mailbox record; and the agent field backstops tasks dispatched before this protocol. The signals are defense in depth, not interchangeable priority fallbacks.

### Decision 3: Deterministic post-write election for overlapping check-ins

**Choice:** After writing a pending marker, Raven rescans its mailbox. If multiple unconfirmed pending markers target the same persona, only the oldest marker by Maildir arrival/`Date` (then `Message-ID` for a tie) proceeds; later markers hold. This uses atomic Maildir delivery without pretending that append alone is a compare-and-swap lock.

**Why:** Two overlapping check-ins can both observe an empty mailbox before either writes. The post-write election ensures at most one of those markers reaches `/api/spawn`; a crashed winner leaves a recoverable pending marker for the next cycle.

### Decision 4: SDD template carries the coordination instructions

**Choice:** The complete token, election, layered-check, and stale-intent pattern is encoded directly in `academy/orders/sdd.md`, with the brief pointer in STANDING_ORDERS.

**Why:** Raven's Captain-loop behavior is prompt-driven from the template and steering. No transport or gateway change is needed.

### Decision 5: Stale dispatch-intent detection via spawn-list state

**Choice:** A confirmed intent is stale when its returned task ID is completed or absent from `kirocrew spawn list`. A pending intent remains blocking through the next check-in; it becomes stale only after a full subsequent check confirms that no task description carries its token and no matching worker is in flight. No dispatch-complete cleanup mail is required.

**Why:** This handles a failed or interrupted spawn without allowing an immediate retry race, while preventing permanently orphaned pending records from blocking future work.

## Risks / Trade-offs

- **[Risk] Mailbox delivery succeeds but the spawn call fails** → The pending marker has no matching task marker or confirmation; after the required follow-up check it becomes stale and a later check-in may retry.
- **[Risk] Raven terminates between intent-write and spawn** → The next check-in sees the pending marker and holds for one confirmation cycle, then recovers when no matching task exists.
- **[Risk] A worker task description is edited or truncated** → The mailbox and agent-field layers still provide backstops; Raven must hold rather than dispatch when any layer is ambiguous.
- **[Trade-off] The template is more procedural** → The extra token, election, and confirmation steps are justified by making the server-assigned-ID boundary and overlapping-check-in behavior explicit.
