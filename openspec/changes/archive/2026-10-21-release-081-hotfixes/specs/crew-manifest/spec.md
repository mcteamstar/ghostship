## MODIFIED Requirements

### Requirement: Selected skills are delivered whole
For every skill the crew manifest selects, `launch` SHALL copy every regular file in that skill's academy directory (symlinks and other special files are skipped) into the crew, keeping the relative layout under the skill's directory, not only its `SKILL.md`. Python bytecode caches SHALL NOT be delivered: any `__pycache__/` directory and any `*.pyc` file under the skill directory are skipped. Files that are executable in the academy SHALL be executable in the crew. Other files SHALL be readable and not executable.

#### Scenario: Skill with a script
- **WHEN** a crew is launched and its manifest selects a skill whose directory holds `SKILL.md` and `scripts/<name>` (executable)
- **THEN** the crew's copy of that skill contains both files, and `scripts/<name>` is executable

#### Scenario: SKILL.md-only skill unchanged
- **WHEN** a selected skill's directory holds only `SKILL.md`
- **THEN** the crew's copy of that skill is the same as before this change

#### Scenario: Bytecode caches are not delivered
- **WHEN** a selected skill's directory holds `scripts/__pycache__/<name>.cpython-313.pyc` left by a local test run
- **THEN** the crew's copy of that skill contains no `__pycache__/` directory and no `.pyc` file
