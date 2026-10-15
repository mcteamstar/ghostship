## Why

`transport/captain.py` contains the check-in scheduling logic, standing-order
mail delivery, cron-registry helpers, and sentinel-file handling that drive the
Captain feature, but its unit-test coverage is limited to the sentinel and
mail-formatting helpers already added in TRN-243/244. The scheduling helpers
(`_captain_checkin_job`, `_captain_standing_view`, `_captain_order_lock`), the
mailbox-count I/O path (`_mail_count`, `_read_all_mail_counts`,
`_read_all_mail_subjects`, `_skim_all_mailboxes`), and the order-template
pipeline (`_list_order_templates`, `_load_order_template`,
`_resolve_order_template`, `_substitute_placeholders`) are untested, creating
blind spots ahead of the trn-242 server modularisation that will move
`_captain_do_order`, `_captain_do_status`, and `_captain_do_stop` into their
own module.

## What Changes

- New file `tests/unit/test_captain.py` covering:
  - `_captain_jobs` / `_captain_checkin_job` — cron-payload normalisation and
    name+agent matching (including `enabled_only` flag).
  - `_captain_standing_view` — response shape, `status` field toggling, registry
    read of `last_checkin_at` / `current_task_id`, and mail-count delegation to
    `FakePodmanClient`.
  - `_captain_order_lock` — returns a `threading.Lock`, same object on repeat
    calls for the same `crew_id`, distinct objects for different crew IDs.
  - `_mail_count` — Maildir (new/ + cur/), legacy mbox fallback, and absent-path
    branches via `FakePodmanClient.set_exec_checked_response`.
  - `_read_all_mail_counts` — JSON decode path and malformed-output fallback.
  - `_read_all_mail_subjects` / `_skim_all_mailboxes` — happy path (JSON from
    exec), fallback to archive API when exec fails, all-8-mailboxes present
    guarantee.
  - `_list_order_templates` / `_load_order_template` — built-in template
    enumeration, alias resolution, `GA_ORDERS_DIR` override precedence, unknown
    template raises `ValueError`.
  - `_resolve_order_template` — `<change>`, `<changes>`, `<change?>` placeholder
    substitution; validation errors for invalid change names; mutual-exclusion
    guards.
  - `_substitute_placeholders` — known tokens replaced; residual
    `{{UNKNOWN}}` token triggers a `WARNING` log.
  - `_append_captain_mail` I/O path — exec called with base64 payload; signed
    vs unsigned mail branch (signing secret present/absent); `Supersedes` header
    threading via registry `last_captain_message_id`.
- No behaviour changes to production code; no new environment variables.

## Capabilities

### New Capabilities

- `transport-test-coverage`: extends the existing spec with requirements for
  `captain.py` scheduling helpers, mailbox I/O helpers, order-template pipeline,
  and `_append_captain_mail` I/O path test coverage.

### Modified Capabilities

- `transport-test-coverage`: adds new `_captain_checkin_job`, `_captain_standing_view`,
  `_captain_order_lock`, `_mail_count`, `_read_all_mail_counts`,
  `_read_all_mail_subjects`, `_skim_all_mailboxes`, `_list_order_templates`,
  `_load_order_template`, `_resolve_order_template`, and `_substitute_placeholders`
  test requirements to the existing spec.

## Impact

- New file: `tests/unit/test_captain.py` (~600–700 lines).
- Existing file unchanged: `transport/captain.py`.
- Existing file unchanged: `tests/unit/conftest.py` (fixtures already sufficient).
- Existing file unchanged: `tests/fakes.py` (`FakePodmanClient` already has all
  required hooks; `set_exec_checked_response` already present).
- No API, schema, or dependency changes.
