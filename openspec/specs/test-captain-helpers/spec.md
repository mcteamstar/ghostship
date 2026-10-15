# test-captain-helpers Specification

## Purpose
Defines the observable test-coverage requirements for the pure-Python helper
functions in `transport/captain.py`, ensuring each helper's contracts are
exercised and regressions are detectable by the unit test suite.

## Requirements

### Requirement: _parse_order_front_matter behaviour

The test suite SHALL verify `_parse_order_front_matter` against the following
observable contracts.

#### Scenario: No front-matter returns whole content as body
- **WHEN** the input has no leading `---` fence
- **THEN** body equals the entire input, description is empty string, aliases is empty list

#### Scenario: description field is parsed and quotes stripped
- **WHEN** front-matter contains `description: "Some text"`
- **THEN** description equals `Some text` with surrounding quotes removed

#### Scenario: aliases field is parsed as a list
- **WHEN** front-matter contains `aliases: ["a", "b"]`
- **THEN** aliases list equals `["a", "b"]`

#### Scenario: body excludes the front-matter block
- **WHEN** front-matter is present
- **THEN** body does not contain the `---` fences or front-matter lines

#### Scenario: unclosed front-matter fence is treated as no front-matter
- **WHEN** the input starts with `---\n` but has no closing `\n---\n`
- **THEN** body equals the entire input and description is empty string

### Requirement: _substitute_placeholders behaviour

The test suite SHALL verify `_substitute_placeholders` replaces all known tokens
and warns on residuals.

#### Scenario: RAVEN_GATEWAY_ORIENTATION token is replaced
- **WHEN** body contains `{{RAVEN_GATEWAY_ORIENTATION}}`
- **THEN** the returned string no longer contains that token and contains non-empty
  replacement text

#### Scenario: RAVEN_SELF_CANCEL token is replaced
- **WHEN** body contains `{{RAVEN_SELF_CANCEL}}`
- **THEN** the returned string no longer contains that token

#### Scenario: RAVEN_STORE_RESOLUTION token is replaced
- **WHEN** body contains `{{RAVEN_STORE_RESOLUTION}}`
- **THEN** the returned string no longer contains that token

#### Scenario: unknown token is left in place
- **WHEN** body contains `{{UNKNOWN_TOKEN}}`
- **THEN** the returned string still contains `{{UNKNOWN_TOKEN}}`

### Requirement: _validate_captain_change_name behaviour

The test suite SHALL verify `_validate_captain_change_name` accepts valid
kebab-case names and rejects invalid ones.

#### Scenario: valid kebab-case name passes
- **WHEN** `change_name` is `"trn-245-test-captain"`
- **THEN** no exception is raised

#### Scenario: uppercase letters are rejected
- **WHEN** `change_name` contains an uppercase letter
- **THEN** `ValueError` is raised

#### Scenario: trailing hyphen is rejected
- **WHEN** `change_name` ends with `-`
- **THEN** `ValueError` is raised

#### Scenario: double hyphen is rejected
- **WHEN** `change_name` contains `--`
- **THEN** `ValueError` is raised

#### Scenario: non-string input is rejected
- **WHEN** `change_name` is `None`
- **THEN** `ValueError` is raised

### Requirement: _resolve_order_template behaviour

The test suite SHALL verify `_resolve_order_template` using a real template
from `academy/orders/` when available, or a temporary directory otherwise.

#### Scenario: None template raises ValueError
- **WHEN** `template` is `None`
- **THEN** `ValueError` is raised

#### Scenario: unknown template name raises ValueError
- **WHEN** `template` is a name that does not exist in any search directory
- **THEN** `ValueError` is raised

#### Scenario: valid template returns non-empty body
- **WHEN** a valid template name is provided (e.g. from `_list_order_templates`)
- **THEN** the returned body is a non-empty string with all known placeholders
  substituted

#### Scenario: body with both change and changes raises ValueError
- **WHEN** a template body contains both `<change>` and `<changes>`
- **THEN** `ValueError` is raised

#### Scenario: template requiring change_name raises when name is None
- **WHEN** a template contains `<change>` and `change_name=None`
- **THEN** `ValueError` is raised

### Requirement: _format_captain_mail behaviour

The test suite SHALL verify `_format_captain_mail` produces correctly structured
RFC 5322 messages with and without signing.

#### Scenario: returned message contains required headers
- **WHEN** `_format_captain_mail` is called with a non-empty body
- **THEN** the returned message string contains `From: admiral@localhost`,
  `To: captain@localhost`, `Subject:`, `Message-ID:`, and `Date:` headers

#### Scenario: message_id is returned as second element
- **WHEN** `_format_captain_mail` is called
- **THEN** the second return value starts with `<` and ends with `@localhost>`

#### Scenario: subject is derived from first non-empty line
- **WHEN** body begins with `This is the subject\nmore body`
- **THEN** the Subject header value is `This is the subject`

#### Scenario: subject is truncated to 72 characters
- **WHEN** the first line of body exceeds 72 characters
- **THEN** the Subject header value is at most 72 characters long

#### Scenario: signing_secret produces X-Admiral-Sig header
- **WHEN** a 32-byte hex signing_secret is provided
- **THEN** the returned message contains an `X-Admiral-Sig:` header

#### Scenario: newline in subject raises ValueError
- **WHEN** the first line of body contains a newline character (injected body)
- **THEN** `ValueError` is raised when signing_secret is provided

#### Scenario: supersedes_id produces Supersedes header
- **WHEN** `supersedes_id` is provided
- **THEN** the returned message contains a `Supersedes:` header with that value

#### Scenario: body appears after blank separator line
- **WHEN** `_format_captain_mail` is called
- **THEN** the headers block and body are separated by a blank line (`\n\n`)

### Requirement: _parse_sentinel_file behaviour

The test suite SHALL verify `_parse_sentinel_file` parses sentinel content into
a dict.

#### Scenario: valid sentinel content is parsed correctly
- **WHEN** content is `"captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\n"`
- **THEN** the returned dict has `captain_id="test-crew"` and
  `completed_at="2026-01-01T00:00:00Z"`

#### Scenario: empty content returns empty dict
- **WHEN** content is an empty string
- **THEN** the returned dict is `{}`

#### Scenario: lines without `=` are skipped
- **WHEN** content contains a line with no `=` character
- **THEN** that line does not appear as a key in the result

### Requirement: _read_sentinel_file behaviour

The test suite SHALL verify `_read_sentinel_file` reads and returns file content
via the Podman archive API, using `FakePodmanClient`.

#### Scenario: returns file content when sentinel exists
- **WHEN** `FakePodmanClient` is scripted with a sentinel tar archive
- **THEN** `_read_sentinel_file` returns the file's decoded content as a string

#### Scenario: returns None when archive API fails
- **WHEN** `FakePodmanClient.container_archive_get` raises an exception
- **THEN** `_read_sentinel_file` returns `None` without raising

### Requirement: _captain_jobs and _captain_checkin_job behaviour

The test suite SHALL verify the job-filtering helpers.

#### Scenario: _captain_jobs returns empty list for non-list payload
- **WHEN** `_captain_jobs` is called with a non-dict or malformed payload
- **THEN** an empty list is returned

#### Scenario: _captain_checkin_job finds the matching job
- **WHEN** a payload contains a job with `name="captain"` and `agent="raven"`
- **THEN** `_captain_checkin_job` returns that job dict

#### Scenario: _captain_checkin_job rejects wrong agent
- **WHEN** a payload contains a job with `name="captain"` but `agent="ghost"`
- **THEN** `_captain_checkin_job` returns `None`

#### Scenario: _captain_checkin_job enabled_only filters disabled jobs
- **WHEN** the matching job has `enabled=False` and `enabled_only=True`
- **THEN** `_captain_checkin_job` returns `None`

### Requirement: _mail_count behaviour

The test suite SHALL verify `_mail_count` returns correct integer counts using
`FakePodmanClient`.

#### Scenario: Maildir with new/ and cur/ files is counted
- **WHEN** `container_exec_checked` returns `"3 2"`
- **THEN** `_mail_count` returns `5`

#### Scenario: mbox format single count is returned
- **WHEN** `container_exec_checked` returns `"7"`
- **THEN** `_mail_count` returns `7`

#### Scenario: unparseable output returns 0
- **WHEN** `container_exec_checked` returns `"invalid output"`
- **THEN** `_mail_count` returns `0`

### Requirement: _captain_order_lock thread-safety

The test suite SHALL verify `_captain_order_lock` returns the same lock instance
for the same `crew_id`.

#### Scenario: same crew_id returns same lock
- **WHEN** `_captain_order_lock` is called twice with the same `crew_id`
- **THEN** the returned lock object is the same instance

#### Scenario: different crew_ids return different locks
- **WHEN** `_captain_order_lock` is called with two different crew_ids
- **THEN** the returned lock objects are different instances
