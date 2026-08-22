# Task Orchestration — Delta Spec (srv-68-raven-decouple)

## Modified Requirement: Task status and collection

Add to the existing "Task status and collection" requirement:

The system SHALL read all crew mailboxes on every `pickup` call (all six persona mailboxes, `/var/mail/captain`, and `/var/mail/admiral`) and include subject lines and counts in the response. Only subject lines are returned — message bodies are not read. Reading mailboxes never modifies them.

What is reported back is tuned to how `pickup` was called:

- When `pickup` is called with a `task_id`: report the task's agent mailbox, captain, and admiral — subjects and counts for those three.
- When `pickup` is called without a `task_id` (crew-wide): report all persona mailboxes, captain, and admiral.

In both cases all 8 mailboxes are read; only the reported set differs.

#### Scenario: Poll a specific task reports agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the response includes the existing fields plus `<agent>_mail: N`, `<agent>_subjects: [...]`, `captain_mail: N`, `captain_subjects: [...]`, `admiral_mail: N`, `admiral_subjects: [...]`

#### Scenario: List all tasks reports all persona, captain, and admiral subjects
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the response includes subject line summaries for all persona mailboxes plus captain and admiral alongside the existing task list
