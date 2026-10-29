## MODIFIED Requirements

### Requirement: slot=True is rejected with a warning in dispatch

When `_resolve_dispatch_slot()` receives `slot=True`, the transport SHALL log a
warning and treat it as `slot=None` (defaulting to the enrolled member slot
behaviour). It SHALL NOT silently produce headless dispatch without any indication
to the caller.

#### Scenario: slot=True logs a warning and resolves as None
- **WHEN** `dispatch()` is called with `slot=True`
- **THEN** the transport logs a WARNING indicating `slot=True` is not a valid value
- **THEN** the dispatch proceeds as if `slot=None` was passed

### Requirement: Cookie update is performed inside the registry lock

(Moved from TRN-283 — this requirement covers the M-2 slot guard only; H-1 cookie
lock fix is in TRN-283.)
