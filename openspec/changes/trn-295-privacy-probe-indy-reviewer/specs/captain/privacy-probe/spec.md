# Spec Delta

## Purpose

Defines the `privacy` standalone Captain template — an on-demand probe that
dispatches a Banshee to scan the whole codebase for internal infrastructure
references that should not appear in a public repository, and mails a
self-contained findings report to the Admiral.

## ADDED Requirements

### Requirement: privacy template dispatches a single Banshee privacy reviewer

When the `privacy` Captain template is ordered, the system SHALL dispatch one
Banshee with task prefix `PRIVACY PROBE <intent_id>` to scan the entire
codebase (source code, docs/, openspec/ specs and changes) for privacy-leaking
content. The template SHALL accept aliases `privacy-probe` and `scrub`.

#### Scenario: Privacy Banshee is dispatched on order

- **WHEN** `captain(crew_id=<id>, action="order", template="privacy")` is sent
- **THEN** Raven dispatches exactly one Banshee with a privacy scan task and records a pending intent marker

#### Scenario: privacy-probe and scrub aliases work identically

- **WHEN** `captain(crew_id=<id>, action="order", template="scrub")` is sent
- **THEN** the system SHALL behave identically to `template="privacy"`

### Requirement: privacy Banshee scans for internal infrastructure references

The privacy Banshee SHALL scan all files in the repository for internal infrastructure references across seven categories, and report each finding with file, line, category, quoted text, and a recommended action.

#### Scenario: Hostname found in source comment

- **WHEN** a source file contains a comment referencing an internal hostname (e.g. `starport.penguin-piano.ts.net`)
- **THEN** the Banshee SHALL include it in the report with category "hostname", the file and line, and recommended action

#### Scenario: RFC-1918 IP address found outside example context

- **WHEN** a source file, config, or doc contains a private IP address (e.g. `192.168.1.50`) outside an explicitly labeled example context
- **THEN** the Banshee SHALL include it in the report with category "ip-address", the file and line, and recommended action

#### Scenario: Example domains and loopback addresses excluded

- **WHEN** a source file uses RFC-standard example domains (`example.com`, `example.org`, `example.net`) or loopback addresses (`localhost`, `127.0.0.1`, `::1`)
- **THEN** the Banshee SHALL NOT include them as findings

#### Scenario: Clean codebase produces empty findings

- **WHEN** no files contain any of the seven categories of internal reference
- **THEN** the Banshee SHALL mail a report stating no privacy findings were identified

### Requirement: privacy standalone template mails findings to admiral@localhost and self-cancels

After completing its scan, the privacy Banshee SHALL mail a self-contained
findings report to `raven@localhost` with subject `privacy probe complete`.
Raven SHALL forward it to `admiral@localhost` and then self-cancel the Captain
check-in.

#### Scenario: Report delivered and Captain self-cancels

- **WHEN** the Banshee mails its report with subject `privacy probe complete`
- **THEN** Raven SHALL forward it to `admiral@localhost` and cancel the standing order
