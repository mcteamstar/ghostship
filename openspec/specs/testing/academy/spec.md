# testing/academy Specification

## Purpose

Defines verification coverage for academy behavior.

## Requirements

### Requirement: academy.py comp registry has error-path tests

`tests/unit/test_academy.py` SHALL cover:
- `_load_comp_registry` with missing file (returns default comps)
- `_load_comp_registry` with malformed JSON (logs error, returns default)
- `AcademyLoader._stage_mcp` with `${VAR}` substitution and missing variable

#### Scenario: _load_comp_registry returns defaults on missing file
- **WHEN** `_load_comp_registry` is called and the registry file does not exist
- **THEN** it returns the default comps without raising

#### Scenario: _load_comp_registry returns defaults on malformed JSON
- **WHEN** `_load_comp_registry` is called and the registry file contains malformed JSON
- **THEN** it logs an error and returns the default comps
