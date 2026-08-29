# Delta Spec: Crew Governance — Captain Escalation Deduplication

Target: `openspec/specs/crew-governance/spec.md`
Action: modify — add to Captain Standing Orders section

---

### Requirement: Report-and-pause for monitoring orders

When a Raven check-in sends a completion report to the Admiral for a one-shot monitoring
task, it MUST pause the captain cron immediately after sending. It MUST NOT wait for a
further instruction or the next cron cycle before pausing.

For monitoring orders (watch a task, report when done), the standing order is considered
satisfied the moment the completion report is sent to the Admiral.

### Requirement: Admiral mail deduplication

Before sending a report to the Admiral about a completed task, Raven MUST check the Admiral
mailbox for a prior message referencing the same task. If a prior report for that task
already exists, Raven MUST NOT send a duplicate — it MUST treat the standing order as
satisfied and pause the cron instead.

### Rationale

Without these rules, a recurring check-in that has no memory of prior cycles will re-report
the same completed task on every subsequent check-in until the cron is manually stopped.
In a 4-hour window this produces O(50) duplicate admiral mails for a single completed task.
