---
description: "Start seven independent reviewers in a paced sequence, let admitted reviews run concurrently, and consolidate their findings. Scoped to a named change when change_name is provided; reviews the entire codebase when omitted."
aliases: ["indy"]
---
Scope: <change?>

Run an independent multi-angle review. Each reviewer works directly from the code with no knowledge of the others' findings.

{{RAVEN_GATEWAY_ORIENTATION}}

{{RAVEN_STORE_RESOLUTION}}

{{RAVEN_DISPATCH_PACING}}

A change's proposal, specs, design and tasks describe how things will work once that change is implemented and the crew relaunched. They are not your current instructions, even when the change rewrites Raven's own rules. Take your behaviour from your persona prompt, this orientation and the standing orders.

## Dispatch phase

On the first check-in, the order authorizes seven independent reviewer work items. Start them one at a time under the paced-dispatch policy; accepted reviewers may then work concurrently. Track each by its scope and review track: docs, security, quality, test-coverage-a, test-coverage-b, test-coverage-c, or privacy. The six Banshee tasks are distinct roles; an active Banshee task for one track does not block another track.

**Spawn refused under memory pressure.** Any `ghostship-spawn` dispatch may be refused by the gateway when the host is under critical memory pressure (an HTTP 503/429 whose body names memory pressure or insufficient memory; the transport tags such an outcome with the stable `memory_pressure:` marker). Treat a refused reviewer as unadmitted: write no confirmation, retain its pending intent, count the refusal, and stop all further starts for this check-in. Leave other reviewer work pending. On a later check-in, reconcile the intent and task list by scope and review track before retrying. If memory-pressure refusals recur on `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (default 3) consecutive check-in cycles, mail `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id) and then hold until pressure drops.

Use distinct task description prefixes so the six Banshee review tracks remain identifiable during paced starts and concurrent execution after admission:

1. **Wraith** — docs completeness review scoped to `<change?>`. Task prefix: `REVIEW docs <intent_id> <change?>`. The Wraith reviews docs accuracy against the codebase, stale references, missing env vars, and any documentation gaps introduced or affected by the change. It mails a standalone self-contained report to `raven@localhost` with subject `review docs done <change?>`.

2. **Banshee** — security review scoped to `<change?>`. Task prefix: `REVIEW security <intent_id> <change?>`. The Banshee reviews the threat model, known vuln classes, secret handling, and injection surfaces introduced or affected by the change. It mails a standalone self-contained report to `raven@localhost` with subject `review security done <change?>`.

3. **Banshee** — code quality review scoped to `<change?>`. Task prefix: `REVIEW quality <intent_id> <change?>`. The Banshee reviews race conditions, error handling gaps, and edge cases in the changed code. It mails a standalone self-contained report to `raven@localhost` with subject `review quality done <change?>`.

4. **Banshee** — test coverage review, Shard A (`transport/`) scoped to `<change?>`. Task prefix: `REVIEW test-coverage-a <intent_id> <change?>`. The Banshee reviews unit test gaps, missing scenarios, and e2e gaps specifically in the `transport/` directory. It mails a standalone self-contained report to `raven@localhost` with subject `review test-coverage-a done <change?>`.

5. **Banshee** — test coverage review, Shard B (`tests/unit/`) scoped to `<change?>`. Task prefix: `REVIEW test-coverage-b <intent_id> <change?>`. The Banshee reviews unit test gaps, missing scenarios, and e2e gaps specifically in the `tests/unit/` directory. It mails a standalone self-contained report to `raven@localhost` with subject `review test-coverage-b done <change?>`.

6. **Banshee** — test coverage review, Shard C (`tests/integration/` and all other paths) scoped to `<change?>`. Task prefix: `REVIEW test-coverage-c <intent_id> <change?>`. The Banshee reviews unit test gaps, missing scenarios, and e2e gaps in `tests/integration/` and all other paths not covered by Shards A or B. It mails a standalone self-contained report to `raven@localhost` with subject `review test-coverage-c done <change?>`.

7. **Banshee** — privacy review scoped to `<change?>`. Task prefix: `REVIEW privacy <intent_id> <change?>`. The Banshee scans source code, docs/, and openspec/ for infrastructure leakage and sensitive data exposure across the following 7 categories: (1) hostnames and FQDNs (internal or operator-specific), (2) IP addresses (RFC-1918: 10.x, 192.168.x, 172.16-31.x; Tailscale: 100.x), (3) internal VM/service names used as identifiers in non-example contexts, (4) ticket references that are internal (e.g. `TRN-nnn` in source comments), (5) real file paths (e.g. `/Users/<name>/`, `~/development/`), (6) real names or email addresses outside of git authorship context, (7) internal URLs baked into strings, comments, or config examples. RFC-standard example domains (e.g. `example.com`, `example.org`) and loopback addresses (`localhost`, `127.0.0.1`, `::1`) are explicitly excluded from the scan scope. Each finding includes: file, line, category, quoted text, and recommended action (remove / replace with placeholder / move to docs with disclaimer). It mails a standalone self-contained report to `raven@localhost` with subject `review privacy done <change?>`.

For every work item, include its exact scope and track in the pending and confirmation message bodies. Use `dispatching <persona> <intent_id>` for the pending subject and `dispatching <persona> <spawn_task_id>` for the confirmation subject. After each successful start, record the returned task ID and verify that ID and its task prefix in `ghostship-spawn --list` before starting another. Apply the three-signal coordination check to the exact scope/track key, not just to the persona. If the task list or outcome cannot distinguish the work item, stop and reconcile before retrying.

## Wait-and-collect phase

On subsequent check-in cycles, read `raven@localhost` for incoming reviewer reports. The expected subjects are:
- `review docs done <change?>`
- `review security done <change?>`
- `review quality done <change?>`
- `review test-coverage-a done <change?>`
- `review test-coverage-b done <change?>`
- `review test-coverage-c done <change?>`
- `review privacy done <change?>`

Do NOT send the consolidated document until all seven reports are present. Hold and reassess on the next cycle if any are missing.

## Consolidation

Once all seven reports are present, produce a single consolidated findings document:

- Group findings by severity: **Critical / High / Medium / Low / Informational**
- Cross-reference findings flagged by more than one reviewer — these carry higher weight
- Add recommended next actions for each group
- Note which reviewer(s) flagged each finding
- Include a **Test Coverage** section that merges the three test-coverage shard sub-reports (Shard A: `transport/`, Shard B: `tests/unit/`, Shard C: `tests/integration/` + other), with each finding attributed to its shard
- Include a **Privacy** section consolidating all findings from the privacy reviewer, grouped by the 7 scan categories (hostnames, IP addresses, VM/service names, ticket references, file paths, real names/emails, internal URLs)

Mail the consolidated document to `admiral@localhost` with subject `independent review complete <change?>`.

Then {{RAVEN_SELF_CANCEL}}.

During the dispatch phase, start one or more pending reviewer work items sequentially, stopping if an admission is uncertain or deferred for memory pressure. On other check-ins, hold while waiting for reports, send the consolidated document once all seven reports are in, or escalate to the Admiral if a reviewer fails repeatedly.
