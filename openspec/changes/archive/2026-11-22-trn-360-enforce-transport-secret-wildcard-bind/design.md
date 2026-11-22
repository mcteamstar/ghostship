# Design

## Context

See proposal.md for motivation. Transport already distinguishes loopback and wildcard addresses, and the missing-secret check is controlled by `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND`. The current check excludes wildcard addresses. The setting defaults to false, and `docs/configuration.md` currently describes only a concrete non-loopback address.

## Goals / Non-Goals

**Goals:**
- Apply the enabled missing-secret guard to every non-loopback bind, including wildcard addresses.
- Keep loopback behavior, secret-present behavior, and the default warn-only setting unchanged.
- Keep the transport secret check separate from portal host and API-key exposure checks.

**Non-Goals:**
- Infer host firewall, Podman port-publication, or network reachability from the bind address.
- Change the default guard value or require a secret for local development when the guard is disabled.

## Decisions

- Classify wildcard addresses as non-loopback for this guard. A wildcard listener can accept connections on external interfaces, so an operator who enables the guard expects startup to fail without the transport secret.
- Keep loopback as the sole bind class exempt from the enabled external-bind guard. Reuse existing address classification rather than adding another network parser.
- Update the configuration documentation to name wildcard binds explicitly. Alternative considered: use the portal's published `HOST` to decide exposure; rejected because the guard protects the Transport-to-Portal boundary and its secret, not portal API-key exposure.

## Risks / Trade-offs

- [Installations that explicitly enable the guard with a wildcard bind but omit the secret will now fail startup] → This is the requested enforcement behavior; the error identifies the missing secret and the operator can configure the secret or disable the guard.
- [A wildcard listener may be isolated by container networking] → The guard remains intentionally conservative and only activates when explicitly enabled; the default remains warn-only.

## Migration Plan

No data migration is required. Existing installations using the default false setting continue with a warning. Operators who enabled the guard must provide `GA_TRANSPORT_SECRET` for wildcard binds. Rollback is reverting the classification change and its documentation/tests.
