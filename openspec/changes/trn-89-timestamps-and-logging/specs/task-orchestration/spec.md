# task-orchestration Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Task dispatch response

The `dispatch` response SHALL include `created_at` (ISO 8601 UTC) in addition to the existing fields. See `task-timestamps/spec.md`.

### Modified Requirement: Task status and collection

The `pickup` response for a specific task SHALL include `created_at`, `started_at`, and `completed_at` timestamp fields. The crew-wide task list SHALL include those fields on each task entry. See `task-timestamps/spec.md`.

Subject lines in `pickup` responses SHALL be structured objects with `subject` and `received_at` fields. See `mail-timestamps/spec.md`.
