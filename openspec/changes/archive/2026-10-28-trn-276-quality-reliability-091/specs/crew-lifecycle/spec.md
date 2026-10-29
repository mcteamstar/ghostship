## MODIFIED Requirements

### Requirement: Waiter timeout is sufficient for worst-case leader restart

The waiter `event.wait(timeout=...)` in `transport/launcher.py` SHALL be set to at
least 150 seconds. The leader restart path under memory pressure can exceed 120
seconds; a shorter timeout causes waiters to raise a spurious 502 while the leader
is still making progress.

#### Scenario: Waiter does not time out during normal leader restart
- **WHEN** a leader restart takes up to 120 seconds to complete
- **THEN** waiters do not raise a timeout error before the leader signals completion

#### Scenario: Waiter timeout is >= 150 seconds
- **WHEN** `transport/launcher.py` is read
- **THEN** the `event.wait(timeout=...)` value is >= 150
