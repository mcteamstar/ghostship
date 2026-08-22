# Crew Manifest Specification

## Purpose

Defines which agents, skills, and steering docs a given crew type includes from the Academy's shared pool, via a manifest file colocated with that crew type's build definition, so a future crew type can select a different combination without any change to transport's copy logic.
## Requirements
### Requirement: Per-crew-type manifest file
The system SHALL define crew composition via a JSON manifest file at `crews/<crew-type>/manifest.json`, with `agents`, `skills`, and `steering` keys. The manifest path SHALL be resolved dynamically from the crew-type registry entry's `dir` field rather than from a hardcoded constant. Each key's value SHALL be either the literal string `"*"` or a JSON array of exact names to include from the corresponding Academy pool: agent `.json` filenames, skill directory names, and steering doc `.md` filenames, respectively.

#### Scenario: kirocrew's manifest selects everything
- **WHEN** the `kirocrew` crew type's `manifest.json` is read
- **THEN** it specifies `"*"` for `agents`, `skills`, and `steering`, matching today's behavior of including every item in each Academy pool

#### Scenario: A different crew type restricts composition
- **WHEN** a `worker` crew type's `manifest.json` specifies `["ghost.json"]` for agents and `["radio", "openspec-apply-change"]` for skills
- **THEN** only those named items are copied into crews launched with `crew_type="worker"`

### Requirement: Manifest-driven copy filtering
The system SHALL filter the set of agent, skill, and steering files copied into a crew during `launch` against that crew type's manifest: copying only the files whose name is listed in an explicit array, or every file in the pool when the manifest specifies `"*"`. The manifest path SHALL be resolved from the crew-type registry entry rather than a global constant.

#### Scenario: Manifest restricts to a subset
- **WHEN** a crew type's manifest specifies an explicit array of agent names instead of `"*"`
- **THEN** only the agent JSON files matching those names are copied into the crew, and every other agent file present in the Academy agents pool is skipped

#### Scenario: Manifest specifies "*"
- **WHEN** a crew type's manifest specifies `"*"` for a given section
- **THEN** every file in that section's Academy pool is copied into the crew, with no filtering applied

### Requirement: Missing or malformed manifest defaults to "*"
The system SHALL treat a missing manifest file, a missing key within an existing manifest, or a manifest that fails to parse as JSON, as equivalent to `"*"` for the affected section(s). The system SHALL log a warning when this happens and SHALL NOT fail crew setup because of it.

#### Scenario: No manifest file present
- **WHEN** a crew type's resolved manifest path does not point to an existing file
- **THEN** `launch` proceeds by copying every agent, skill, and steering file in the respective Academy pools, exactly as if the manifest specified `"*"` for each, and a warning is logged

#### Scenario: Manifest is present but malformed
- **WHEN** a crew type's `manifest.json` exists but is not valid JSON
- **THEN** `launch` proceeds as if the manifest specified `"*"` for every section, and a warning is logged, rather than failing crew setup

