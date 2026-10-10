## MODIFIED Requirements

### Requirement: Captain dispatch uses a compatible model on Claude-backend crews

When the system dispatches a Captain check-in on a crew whose configured
`acp_backend` is `"claude"` (or whose crew-level default model is a Claude model),
and no explicit model override is provided by the Captain order, the system SHALL
derive the dispatch model from the crew's configured default model rather than
relying on the `raven.json` `"model"` field. This ensures Raven is always dispatched
on a model that is compatible with the backend's capabilities.

The `raven.json` `"model"` field is a default for non-Claude backend crews; it SHALL
NOT be used as the dispatch model when the crew runs on a Claude backend.

#### Scenario: Captain check-in on Claude-backend crew uses crew model

- **WHEN** `_dispatch_captain_checkin` is called for a crew with `acp_backend="claude"`
  and the caller passes `model=None`
- **THEN** the spawn request includes `"model": <crew_default_model>` derived from the
  crew's registry entry, not a GPT model string from `raven.json`

#### Scenario: Explicit model override is respected

- **WHEN** `_dispatch_captain_checkin` is called with an explicit non-None `model`
  parameter
- **THEN** the spawn request uses that explicit model, regardless of the crew's
  configured backend or default model

#### Scenario: Non-Claude crew unaffected

- **WHEN** `_dispatch_captain_checkin` is called for a crew that does not use the
  Claude backend, with `model=None`
- **THEN** the spawn request is built exactly as before (no `"model"` key from the
  crew registry is added; gateway picks the default)
