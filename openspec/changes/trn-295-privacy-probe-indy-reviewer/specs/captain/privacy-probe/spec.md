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

The privacy Banshee SHALL scan all files in the repository for the following
categories of internal reference and report each finding with file, line,
category, quoted text, and a recommended action (remove / replace with
placeholder / move to docs with disclaimer):

1. Hostnames and FQDNs that are operator-specific or internal
2. IP addresses in RFC-1918 ranges (10.x, 192.168.x, 172.16–31.x) or Tailscale range (100.x)
3. Internal VM or service names used as identifiers outside of example/placeholder context
4. Internal ticket identifiers in source comments or non-changelog prose
5. Real filesystem paths containing a username or development directory
6. Real names or email addresses outside of git authorship context
7. Internal URLs baked into source strings, comments, or config examples

#### Scenario: Hostname found in source comment

- **WHEN** a source file contains a comment referencing an internal hostname (e.g. `starport.penguin-piano.ts.net`)
- **THEN** the Banshee SHALL include it in the report with category "hostname", the file and line, and recommended action

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
