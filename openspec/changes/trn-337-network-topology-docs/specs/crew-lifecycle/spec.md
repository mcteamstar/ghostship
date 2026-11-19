# Spec Delta

## MODIFIED Requirements

### Requirement: Crew and resource naming convention

The system SHALL name every crew-scoped Podman resource with a gs- prefix derived from the crew_id, kept entirely separate from the ga- prefix used for fixed Ghost Academy infrastructure (ga-transport, ga-portside, ga-starboard) — so a crew_id can never collide with a fixed infrastructure name, regardless of what the caller picks.

#### Scenario: Resource names for a crew
- **WHEN** a crew is created for crew_id
- **THEN** its container is named gs-<crew_id>, its workspace volume gs-vol-<crew_id>, its home volume gs-home-<crew_id>, and it joins the shared ga-starboard network

#### Scenario: crew_id matching an infra name
- **WHEN** a crew is created with crew_id equal to transport or starboard
- **THEN** the resulting crew container does not collide with fixed ga-transport or the ga-starboard network because ga- and gs- are different prefixes
