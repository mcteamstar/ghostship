# Spec Delta

## MODIFIED Requirements

### Requirement: External bind guard checks the transport secret and bind
When `GA_TRANSPORT_SECRET` is absent and `GA_TRANSPORT_BIND` is a non-loopback address, including a wildcard address, Transport SHALL refuse to start when `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true`. When the flag is unset or false, Transport SHALL emit a critical warning and continue in pass-through mode. The guard SHALL evaluate `GA_TRANSPORT_BIND` and `GA_TRANSPORT_SECRET`; it SHALL NOT treat the portal's `HOST` or `GA_API_KEY` as inputs to this check.

#### Scenario: Explicit external bind refuses startup when guard is enabled
- **WHEN** `GA_TRANSPORT_BIND` is a specific non-loopback address, `GA_TRANSPORT_SECRET` is absent, and `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true`
- **THEN** Transport logs a critical error and exits without starting

#### Scenario: Wildcard bind refuses startup when guard is enabled
- **WHEN** `GA_TRANSPORT_BIND` is a wildcard address, `GA_TRANSPORT_SECRET` is absent, and `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true`
- **THEN** Transport logs a critical error and exits without starting

#### Scenario: Explicit external bind warns when guard is disabled
- **WHEN** `GA_TRANSPORT_BIND` is a specific non-loopback or wildcard address, `GA_TRANSPORT_SECRET` is absent, and the guard is unset or false
- **THEN** Transport logs a critical warning and continues in pass-through mode

#### Scenario: Loopback or wildcard bind does not trigger the explicit external-bind guard
- **WHEN** `GA_TRANSPORT_BIND` is loopback and the secret is absent, or is wildcard and the secret is present
- **THEN** the external-bind guard does not refuse startup
- **AND** when the loopback bind has no secret, Transport logs that the secret is absent and middleware is in pass-through mode

#### Scenario: Secret present permits wildcard bind
- **WHEN** `GA_TRANSPORT_BIND` is a wildcard address and `GA_TRANSPORT_SECRET` is present
- **THEN** the missing-secret guard does not refuse startup

#### Scenario: API key and portal bind do not substitute for the transport secret
- **WHEN** the portal `HOST` or `GA_API_KEY` changes while `GA_TRANSPORT_BIND` and `GA_TRANSPORT_SECRET` remain unchanged
- **THEN** the external-bind guard result is unchanged
