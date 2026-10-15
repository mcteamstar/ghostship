## ADDED Requirements

### Requirement: _captain_checkin_job / _captain_jobs test coverage
The test suite SHALL exercise `_captain_jobs` and `_captain_checkin_job` using
inline cron-listing payloads, verifying name+agent matching, `enabled_only`
filtering, and graceful handling of malformed or empty payloads.

#### Scenario: _captain_jobs normalises dict payload
- **WHEN** `_captain_jobs` receives a dict with a `jobs` key containing a list
- **THEN** it returns that list of job dicts

#### Scenario: _captain_jobs normalises list payload
- **WHEN** `_captain_jobs` receives a list directly
- **THEN** it returns that list unchanged

#### Scenario: _captain_checkin_job matches on name and agent
- **WHEN** `_captain_checkin_job` is given a payload containing a job with `name="captain"` and `agent="raven"`
- **THEN** it returns that job dict

#### Scenario: _captain_checkin_job ignores wrong agent
- **WHEN** `_captain_checkin_job` is given a job with `name="captain"` and `agent="ghost"`
- **THEN** it returns None

#### Scenario: _captain_checkin_job enabled_only filters disabled jobs
- **WHEN** `_captain_checkin_job` is called with `enabled_only=True` and the matching job has `enabled=False`
- **THEN** it returns None

#### Scenario: _captain_checkin_job returns None for empty payload
- **WHEN** `_captain_checkin_job` is given an empty cron listing
- **THEN** it returns None

### Requirement: _captain_order_lock test coverage
The test suite SHALL exercise `_captain_order_lock`, verifying identity and
isolation guarantees.

#### Scenario: Same crew_id returns the same lock
- **WHEN** `_captain_order_lock` is called twice with the same crew_id
- **THEN** both calls return the same `threading.Lock` object

#### Scenario: Different crew_ids return distinct locks
- **WHEN** `_captain_order_lock` is called with two different crew_ids
- **THEN** the returned locks are different objects

#### Scenario: Returned value is a threading.Lock
- **WHEN** `_captain_order_lock` is called with any crew_id
- **THEN** the returned object is a `threading.Lock` instance

### Requirement: _captain_standing_view test coverage
The test suite SHALL exercise `_captain_standing_view` covering response shape,
status field toggling, and registry reads of scheduling metadata.

#### Scenario: Returns dict with required keys
- **WHEN** `_captain_standing_view` is called with a valid job dict and a FakePodmanClient
- **THEN** the result contains `crew_id`, `action`, `status`, `enabled`, `job_id`, `last_run`, `unread_mail`, `mailbox`, `unread_admiral_mail`, and `admiral_mailbox` keys

#### Scenario: status is "enabled" when job enabled=True
- **WHEN** the job dict has `enabled=True`
- **THEN** `status` is `"enabled"`

#### Scenario: status is "paused" when job enabled=False
- **WHEN** the job dict has `enabled=False`
- **THEN** `status` is `"paused"`

#### Scenario: last_checkin_at read from registry schedule entry
- **WHEN** the registry contains a captain schedule entry for the crew with `last_checkin_at` set
- **THEN** `_captain_standing_view` returns that value in `last_checkin_at`

#### Scenario: current_task_id read from registry schedule entry
- **WHEN** the registry contains a captain schedule entry with `current_task_id` set
- **THEN** `_captain_standing_view` returns that value in `current_task_id`

### Requirement: _mail_count test coverage
The test suite SHALL exercise `_mail_count` covering Maildir, legacy mbox, and
absent-path branches via `FakePodmanClient.set_exec_checked_response`.

#### Scenario: Maildir counts new/ and cur/ messages
- **WHEN** `container_exec_checked` returns `"3 2"` (new/ count + cur/ count)
- **THEN** `_mail_count` returns 5

#### Scenario: Legacy mbox returns single count
- **WHEN** `container_exec_checked` returns a single integer string `"7"`
- **THEN** `_mail_count` returns 7

#### Scenario: Absent mailbox returns zero
- **WHEN** `container_exec_checked` returns `"0 0"`
- **THEN** `_mail_count` returns 0

#### Scenario: Malformed output returns zero
- **WHEN** `container_exec_checked` returns non-numeric output
- **THEN** `_mail_count` returns 0 without raising

### Requirement: _read_all_mail_counts test coverage
The test suite SHALL exercise `_read_all_mail_counts` covering the JSON decode
path and malformed-output fallback.

#### Scenario: Valid JSON response returns count dict
- **WHEN** `container_exec_checked` returns a JSON object mapping mailbox names to integer counts
- **THEN** `_read_all_mail_counts` returns that mapping with counts as integers

#### Scenario: Malformed JSON returns empty dict
- **WHEN** `container_exec_checked` returns non-JSON output
- **THEN** `_read_all_mail_counts` returns an empty dict without raising

#### Scenario: Zero counts are omitted
- **WHEN** the JSON response contains an entry with count 0
- **THEN** `_read_all_mail_counts` omits that entry from the result

### Requirement: _read_all_mail_subjects and _skim_all_mailboxes test coverage
The test suite SHALL exercise `_read_all_mail_subjects` and `_skim_all_mailboxes`
covering the happy path (exec returns JSON), exec-failure fallback to archive
API, and the all-8-mailboxes guarantee.

#### Scenario: _read_all_mail_subjects returns subject dicts from JSON
- **WHEN** `container_exec_checked` returns a JSON object mapping mailbox names to lists of subject dicts
- **THEN** `_read_all_mail_subjects` returns that mapping

#### Scenario: _skim_all_mailboxes returns all 8 mailbox keys
- **WHEN** `_skim_all_mailboxes` succeeds (exec returns valid JSON)
- **THEN** the result contains exactly the keys ghost, spectre, banshee, wraith, reaper, raven, captain, admiral

#### Scenario: _skim_all_mailboxes falls back to archive API on exec failure
- **WHEN** `container_exec_checked` raises an exception
- **THEN** `_skim_all_mailboxes` falls back to `container_archive_get` per mailbox and returns an empty list per mailbox rather than raising

### Requirement: _list_order_templates and _load_order_template test coverage
The test suite SHALL exercise `_list_order_templates` and `_load_order_template`
covering built-in template enumeration, alias resolution, `GA_ORDERS_DIR`
override precedence, and unknown-template error handling.

#### Scenario: _list_order_templates returns at least one built-in template
- **WHEN** `_list_order_templates` is called with no GA_ORDERS_DIR override
- **THEN** the result is a non-empty list of (name, description) tuples

#### Scenario: _load_order_template returns body for known template
- **WHEN** `_load_order_template` is called with a template name that exists in academy/orders/
- **THEN** it returns a (description, body) tuple where body is a non-empty string

#### Scenario: _load_order_template raises ValueError for unknown template
- **WHEN** `_load_order_template` is called with a template name that does not exist
- **THEN** it raises ValueError

#### Scenario: GA_ORDERS_DIR user template overrides built-in on same stem
- **WHEN** `GA_ORDERS_DIR` points to a directory containing a template with the same stem as a built-in
- **THEN** `_list_order_templates` reports the user-defined template's description, not the built-in's

#### Scenario: GA_ORDERS_DIR missing logs one warning
- **WHEN** `GA_ORDERS_DIR` is set to a path that does not exist
- **THEN** `_list_order_templates` logs exactly one WARNING and returns only built-in templates

### Requirement: _resolve_order_template test coverage
The test suite SHALL exercise `_resolve_order_template` covering placeholder
substitution rules and validation error paths.

#### Scenario: <change> placeholder replaced with change_name
- **WHEN** a template body contains `<change>` and `change_name` is provided
- **THEN** the returned body contains the change_name in place of `<change>`

#### Scenario: <change> without change_name raises ValueError
- **WHEN** a template body contains `<change>` and `change_name` is None
- **THEN** `_resolve_order_template` raises ValueError

#### Scenario: <change?> replaced with change_name when provided
- **WHEN** a template body contains `<change?>` and `change_name` is provided
- **THEN** the returned body contains the change_name

#### Scenario: <change?> replaced with "entire codebase" when change_name is None
- **WHEN** a template body contains `<change?>` and `change_name` is None
- **THEN** the returned body contains "entire codebase"

#### Scenario: Invalid change_name raises ValueError
- **WHEN** a template body contains `<change>` and `change_name` contains uppercase letters
- **THEN** `_resolve_order_template` raises ValueError

#### Scenario: None template raises ValueError
- **WHEN** `_resolve_order_template` is called with `template=None`
- **THEN** it raises ValueError

### Requirement: _substitute_placeholders test coverage
The test suite SHALL exercise `_substitute_placeholders` covering known token
replacement and residual-placeholder warning behaviour.

#### Scenario: Known tokens are replaced
- **WHEN** `_substitute_placeholders` is called with a body containing `{{RAVEN_GATEWAY_ORIENTATION}}`
- **THEN** the result contains the full `_RAVEN_GATEWAY_ORIENTATION` constant text

#### Scenario: Residual unknown token triggers WARNING log
- **WHEN** `_substitute_placeholders` is called with a body containing `{{UNKNOWN_TOKEN}}`
- **THEN** a WARNING is logged identifying the residual placeholder

### Requirement: _append_captain_mail I/O path test coverage (extended)
The test suite SHALL exercise `_append_captain_mail` covering: exec called with
base64 payload; signed vs unsigned mail when signing secret is present or absent;
and `Supersedes` header threading via registry `last_captain_message_id`.

#### Scenario: _append_captain_mail calls container_exec_checked with base64 payload
- **WHEN** `_append_captain_mail` is called
- **THEN** `container_exec_checked` is called and the command includes a base64-encoded mail message

#### Scenario: Unsigned mail written when no signing secret
- **WHEN** `_append_captain_mail` is called for a crew that has no signing secret in the registry
- **THEN** the delivered message does NOT contain an `X-Admiral-Sig` header

#### Scenario: Supersedes header present when last_captain_message_id is set
- **WHEN** the registry crew entry has `last_captain_message_id` set
- **THEN** the delivered message contains a `Supersedes:` header referencing that message ID
