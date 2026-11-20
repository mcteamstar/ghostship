# Crew Manifest Specification

## Purpose

Defines which agents, skills, and steering docs a given crew type includes from the Academy's shared pool, via a manifest file colocated with that crew type's build definition, so a future crew type can select a different combination without any change to transport's copy logic.

## Requirements

### Requirement: Per-crew-type manifest file

Each crew type SHALL define `agents`, `skills`, and `steering` in `crews/<type>/manifest.json`, resolved from its registry `dir`. Each value SHALL be `"*"` or exact Academy pool names (agent JSON files, skill directories, or steering Markdown files).

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

A missing manifest, missing section, or invalid JSON SHALL default the affected section to `"*"`, log a warning, and not fail crew setup.

#### Scenario: No manifest file present
- **WHEN** a crew type's resolved manifest path does not point to an existing file
- **THEN** `launch` proceeds by copying every agent, skill, and steering file in the respective Academy pools, exactly as if the manifest specified `"*"` for each, and a warning is logged

#### Scenario: Manifest is present but malformed
- **WHEN** a crew type's `manifest.json` exists but is not valid JSON
- **THEN** `launch` proceeds as if the manifest specified `"*"` for every section, and a warning is logged, rather than failing crew setup

### Requirement: Transport validates manifest references at startup

At startup, the transport SHALL warn when a registered manifest names an agent, skill, or steering file absent from its Academy pool; the warning SHALL identify the crew type, name, and expected pool.

#### Scenario: Startup validation warns on unknown agent name
- **WHEN** the transport starts and a manifest lists an agent name that has no corresponding `.json` file in the Academy agents pool
- **THEN** a startup warning is logged identifying the crew type and the unknown name; crew setup for that crew type is not prevented

#### Scenario: Startup validation passes for valid manifests
- **WHEN** the transport starts and all manifests reference only names that exist in their respective Academy pools
- **THEN** no validation warning is logged for manifests
### Requirement: Selected skills are delivered whole

For each selected skill, `launch` SHALL copy every regular file with its relative layout, skipping symlinks, special files, and Python bytecode. Academy executable bits SHALL be preserved; other delivered files SHALL be readable and non-executable.

#### Scenario: Skill with a script
- **WHEN** a crew is launched and its manifest selects a skill whose directory holds `SKILL.md` and `scripts/<name>` (executable)
- **THEN** the crew's copy of that skill contains both files, and `scripts/<name>` is executable

#### Scenario: SKILL.md-only skill unchanged
- **WHEN** a selected skill's directory holds only `SKILL.md`
- **THEN** the crew's copy of that skill is the same as before this change

#### Scenario: Bytecode caches are not delivered
- **WHEN** a selected skill's directory holds `scripts/__pycache__/<name>.cpython-313.pyc` left by a local test run
- **THEN** the crew's copy of that skill contains no `__pycache__/` directory and no `.pyc` file
