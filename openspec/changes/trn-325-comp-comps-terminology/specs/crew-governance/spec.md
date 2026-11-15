# Spec Delta

## MODIFIED Requirements

### Requirement: Transport injects per-crew security policy at setup

The transport SHALL inject a `security_policy.json` into `~/.kiro/crew/security_policy.json` inside each crew container after the gateway is ready and the `admiral_secret` has been written. The policy SHALL be selected by the resolved crew `comp`, falling back to the `default` template when no comp-specific template exists. The legacy `composition` launch argument remains an alias: matching values resolve to the same comp, while conflicting values make launch fail before policy selection. Policy templates live in `academy/policies/` and are available to the transport from `/policies/`.

#### Scenario: Policy injected for new crew with known comp
- **WHEN** `launch(crew_id, composition="kirocrew")` completes setup using the legacy alias
- **THEN** `~/.kiro/crew/security_policy.json` exists in the container with the `kirocrew` comp's policy content (or default if no specific template), and the `launch()` response includes `policy_version`

#### Scenario: Policy injection falls back to default for unknown comp
- **WHEN** `launch(crew_id, composition="custom-unknown")` completes setup using the legacy alias
- **THEN** the default policy template is used and injected successfully; no error is raised for a missing comp template

#### Scenario: Policy injection failure is logged but does not abort launch
- **WHEN** the policy file write inside the container fails (e.g. permissions)
- **THEN** the failure is logged as a warning and `launch()` continues; `policy_version` is omitted from the response

#### Scenario: Matching comp and composition select the same template
- **WHEN** `launch(crew_id, comp="kirocrew", composition="kirocrew")` completes setup
- **THEN** the `kirocrew` policy template is selected and injected

#### Scenario: Conflicting comp and composition block policy resolution
- **WHEN** `launch(crew_id, comp="kirocrew", composition="spec-ops")` is called
- **THEN** launch returns a clear error before policy template resolution, and no policy file is written
