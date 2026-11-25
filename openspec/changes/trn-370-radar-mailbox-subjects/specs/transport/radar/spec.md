# Spec Delta

## ADDED Requirements

### Requirement: Radar shows crew mailbox subjects
Radar SHALL show subject strings grouped by mailbox in a crew's expanded detail. It SHALL fetch them on demand and SHALL expose no message bodies or message metadata beyond mailbox names and subjects.

#### Scenario: Subjects are loaded when crew detail opens
- **WHEN** an operator expands a registered crew's detail
- **THEN** Radar fetches and displays subjects from `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral` without adding mailbox reads to the fleet polling request

#### Scenario: Subjects remain available for stopped crews
- **WHEN** an operator expands a stopped crew's detail and its mailbox files are readable
- **THEN** Radar displays the same mailbox subjects available for a running crew
- **THEN** reading the subjects does not alter or consume any mailbox messages

#### Scenario: Empty mailbox
- **WHEN** a crew mailbox has no messages with a subject
- **THEN** Radar displays an explicit empty state for that mailbox

#### Scenario: Mailbox subjects cannot be loaded
- **WHEN** the mailbox-subject request fails
- **THEN** Radar displays a single unavailable state for the crew's mailboxes without presenting any mailbox as empty

#### Scenario: Browser request requires the Portal session
- **WHEN** an unauthenticated browser requests crew mailbox subjects while API-key authentication is enabled
- **THEN** the existing Portal session gate prevents the request from reaching Radar and no mailbox data is returned

### Requirement: Transport provides a protected subject-only mailbox endpoint
Transport SHALL expose a portside-internal, transport-secret-protected endpoint that returns each registered crew's mailbox names and subject strings only. It SHALL leave mailbox messages unchanged.

#### Scenario: Read subjects from a registered crew
- **WHEN** Radar requests a registered crew's mailbox subjects with a valid `X-Transport-Token`
- **THEN** Transport returns `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral`, each mapped to a list of subject strings
- **THEN** the response contains no message bodies, sender details, timestamps, or separate count fields

#### Scenario: Subjects are ordered and bounded
- **WHEN** a mailbox holds more than 50 messages with subjects
- **THEN** Transport returns that mailbox's 50 most recently delivered subjects, newest first
- **THEN** each subject is at most 200 characters

#### Scenario: Mailbox has never been created
- **WHEN** a registered crew has no directory or file for one of the eight mailboxes (for example, a stopped crew that has never received `admiral` mail)
- **THEN** Transport returns an empty list for that mailbox and does not report the crew's mailboxes as unavailable

#### Scenario: Registered crew's container no longer exists
- **WHEN** Radar requests subjects for a registered crew whose container has been removed
- **THEN** Transport returns an error response that Radar can display as unavailable, and does not return empty mailboxes

#### Scenario: Read subjects for a stopped crew
- **WHEN** Radar requests subjects for a registered stopped crew with a valid `X-Transport-Token`
- **THEN** Transport returns subjects from readable mailbox files without starting the crew

#### Scenario: Unknown crew
- **WHEN** Radar requests mailbox subjects for an unregistered crew
- **THEN** Transport returns HTTP 404

#### Scenario: Missing or invalid transport secret
- **WHEN** a request omits or supplies an invalid `X-Transport-Token`
- **THEN** Transport rejects the request without returning mailbox data

#### Scenario: Mailbox source is unavailable
- **WHEN** Transport cannot read any existing mailbox of a registered crew, or cannot reach the crew's container filesystem
- **THEN** Transport returns an error response for the whole request that Radar can display as unavailable, rather than reporting any mailbox as empty or returning a partial result
