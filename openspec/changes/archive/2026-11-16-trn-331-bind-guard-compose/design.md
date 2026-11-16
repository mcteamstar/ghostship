# Design

## Context

YAML resolution already maps `network.require_secret_on_external_bind` to `GA_REQUIRE_SECRET_ON_EXTERNAL_BIND`, and Transport reads that environment variable. The generated Compose environment omits it. The runtime guard applies to a specific non-loopback, non-wildcard `GA_TRANSPORT_BIND` when `GA_TRANSPORT_SECRET` is absent; this is separate from the portal API-key check. The README's all-interfaces default statement is stale.

## Goals / Non-Goals

**Goals:**
- Carry the existing setting through the generated `ga-transport` environment.
- Make docs describe the actual guard and the existing loopback portal default.
- Cover config resolution, Compose output, and the runtime decision branches.

**Non-Goals:**
- Change the default `GA_TRANSPORT_BIND`, which Compose intentionally sets to `0.0.0.0` inside its container.
- Change the separate API-key requirement based on the host address where Caddy publishes.

## Decisions

- Add the guard to `ComposeConfig`, environment resolution, and `transport_environment` using the existing YAML mapping and default. This keeps installer output and runtime settings on the same configuration path.
- Update `docs/configuration.md` to name `GA_TRANSPORT_BIND` and `GA_TRANSPORT_SECRET`, including the specific-address condition and warn-only default. Update the README to say Caddy publishes on loopback by default; remote exposure requires an explicit bind and the existing API-key/opt-out policy.
- Keep testing focused at the generated-environment boundary and startup-check boundary. No install migration is needed because the setting already exists in resolved config; rerunning install regenerates Compose.

## Risks / Trade-offs

- [Risk] The word "external" may be read as applying to the wildcard `0.0.0.0` bind used inside Compose → Document the current code's loopback, wildcard, and specific-address cases explicitly.
- [Risk] API-key and transport-secret guards are easy to conflate → Keep separate documentation rows and tests for portal exposure and transport middleware protection.
