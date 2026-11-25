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
- **THEN** Radar displays an unavailable state without presenting the mailbox as empty

#### Scenario: Browser request requires the Portal session
- **WHEN** an unauthenticated browser requests crew mailbox subjects while API-key authentication is enabled
- **THEN** the existing Portal session gate prevents the request from reaching Radar and no mailbox data is returned

### Requirement: Transport provides a protected subject-only mailbox endpoint
Transport SHALL expose a portside-internal, transport-secret-protected endpoint that returns each registered crew's mailbox names and subject strings only. It SHALL leave mailbox messages unchanged.

#### Scenario: Read subjects from a registered crew
- **WHEN** Radar requests a registered crew's mailbox subjects with a valid `X-Transport-Token`
- **THEN** Transport returns `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral`, each mapped to a list of subject strings
- **THEN** the response contains no message bodies, sender details, timestamps, or counts

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
- **WHEN** Transport cannot read a registered crew's mailbox files
- **THEN** Transport returns an error that Radar can display as unavailable, rather than reporting an empty mailbox
