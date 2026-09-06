---
description: "Dispatch four concurrent independent reviewers scoped to a named change and consolidate their findings."
---
Scope: change <change>

Run an independent multi-angle review of the named change. Each reviewer works directly from the code with no knowledge of the others' findings.

{{RAVEN_GATEWAY_ORIENTATION}}

{{RAVEN_STORE_RESOLUTION}}

## Dispatch phase

On the first check-in, dispatch all four reviewers concurrently. Use the standard intent/idempotency protocol for each dispatch — write a pending intent marker to `raven@localhost` before calling `/api/spawn`, then confirm with the spawn task ID.

Use distinct task description prefixes so three concurrent Banshee tasks can be tracked without false-positive duplicate detection:

1. **Wraith** — docs completeness review scoped to `<change>`. Task prefix: `REVIEW docs <intent_id> <change>`. The Wraith reviews docs accuracy against the codebase, stale references, missing env vars, and any documentation gaps introduced or affected by the change. It mails a standalone self-contained report to `raven@localhost` with subject `review docs done <change>`.

2. **Banshee** — security review scoped to `<change>`. Task prefix: `REVIEW security <intent_id> <change>`. The Banshee reviews the threat model, known vuln classes, secret handling, and injection surfaces introduced or affected by the change. It mails a standalone self-contained report to `raven@localhost` with subject `review security done <change>`.

3. **Banshee** — code quality review scoped to `<change>`. Task prefix: `REVIEW quality <intent_id> <change>`. The Banshee reviews race conditions, error handling gaps, and edge cases in the changed code. It mails a standalone self-contained report to `raven@localhost` with subject `review quality done <change>`.

4. **Banshee** — test coverage review scoped to `<change>`. Task prefix: `REVIEW test-coverage <intent_id> <change>`. The Banshee reviews unit test gaps, missing scenarios, and e2e gaps for the changed code. It mails a standalone self-contained report to `raven@localhost` with subject `review test-coverage done <change>`.

Apply the standard three-signal dispatch-coordination check (mailbox primary, task-description secondary, agent-field tertiary) for each dispatch. The task description prefix differentiates the three Banshee tasks — check for the specific prefix, not just `agent: banshee`.

## Wait-and-collect phase

On subsequent check-in cycles, read `raven@localhost` for incoming reviewer reports. The expected subjects are:
- `review docs done <change>`
- `review security done <change>`
- `review quality done <change>`
- `review test-coverage done <change>`

Do NOT send the consolidated document until all four reports are present. Hold and reassess on the next cycle if any are missing.

## Consolidation

Once all four reports are present, produce a single consolidated findings document:

- Group findings by severity: **Critical / High / Medium / Low / Informational**
- Cross-reference findings flagged by more than one reviewer — these carry higher weight
- Add recommended next actions for each group
- Note which reviewer(s) flagged each finding

Mail the consolidated document to `admiral@localhost` with subject `independent review complete <change>`.

Then {{RAVEN_SELF_CANCEL}}.

Each check-in takes exactly one action: dispatch the next pending reviewer (if any remain), hold while waiting for reports, send the consolidated document once all four reports are in, or escalate to the Admiral if a reviewer fails repeatedly.
