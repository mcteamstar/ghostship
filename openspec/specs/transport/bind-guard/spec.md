# Transport Bind Guard Specification

## Purpose

Defines how Transport protects an explicitly configured non-loopback bind when its internal transport secret is absent, and ensures installation settings reach the running container.

## Requirements

### Requirement: External bind guard checks the transport secret and bind
When `GA_TRANSPORT_SECRET` is absent and `GA_TRANSPORT_BIND` is a specific non-loopback, non-wildcard address, Transport SHALL refuse to start when `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true`. When the flag is unset or false, Transport SHALL emit a critical warning and continue in pass-through mode. The guard SHALL evaluate `GA_TRANSPORT_BIND` and `GA_TRANSPORT_SECRET`; it SHALL NOT treat the portal's `HOST` or `GA_API_KEY` as inputs to this check.

#### Scenario: Explicit external bind refuses startup when guard is enabled
- **WHEN** `GA_TRANSPORT_BIND` is a specific non-loopback address, `GA_TRANSPORT_SECRET` is absent, and `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true`
- **THEN** Transport logs a critical error and exits without starting

#### Scenario: Explicit external bind warns when guard is disabled
- **WHEN** `GA_TRANSPORT_BIND` is a specific non-loopback address, `GA_TRANSPORT_SECRET` is absent, and the guard is unset or false
- **THEN** Transport logs a critical warning and continues in pass-through mode

#### Scenario: Loopback or wildcard bind does not trigger the explicit external-bind guard
- **WHEN** `GA_TRANSPORT_BIND` is loopback or wildcard and `GA_TRANSPORT_SECRET` is absent
- **THEN** the explicit external-bind guard does not refuse startup
- **THEN** Transport logs that the secret is absent and middleware is in pass-through mode

#### Scenario: API key and portal bind do not substitute for the transport secret
- **WHEN** the portal `HOST` or `GA_API_KEY` changes while `GA_TRANSPORT_BIND` and `GA_TRANSPORT_SECRET` remain unchanged
- **THEN** the external-bind guard result is unchanged

### Requirement: Installer passes external-bind guard into Transport
The installer SHALL preserve the resolved `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND` value in the generated Compose environment for `ga-transport`, so the value used to configure an installation is also used by the running Transport container.

#### Scenario: YAML guard setting reaches the running service configuration
- **WHEN** `network.require_secret_on_external_bind` resolves to `true`
- **THEN** generated Compose sets `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND=true` for `ga-transport`

#### Scenario: Default guard value reaches the running service configuration
- **WHEN** the guard setting is unset
- **THEN** generated Compose passes the configured default `false` for `ga-transport`
