## ADDED Requirements

### Requirement: Readable mailbox delivery metadata
Radar SHALL prioritize the subject, show sender and recipient clearly, and make the full sender address accessible when a shorter label is shown.

#### Scenario: Local address carries a task suffix
- **WHEN** a delivery has a recognized task-qualified local sender
- **THEN** the sender label is concise and the full sender remains available
- **AND** sender grouping preserves distinct addresses

#### Scenario: Timestamp is unavailable
- **WHEN** a delivery has no valid timestamp
- **THEN** the chronological view places it in a clearly labeled undated group after dated deliveries

### Requirement: Search retained mailbox history
Radar SHALL provide case-insensitive search over retained subjects, sender identities and recipients in the selected crew.

#### Scenario: Search with grouping enabled
- **WHEN** the operator searches in any grouping mode
- **THEN** only matching deliveries are shown, with the selected grouping and applicable retention notice

#### Scenario: No deliveries match
- **WHEN** a query produces no matches in a nonempty snapshot
- **THEN** Radar shows a no-match state and a clear-search action
