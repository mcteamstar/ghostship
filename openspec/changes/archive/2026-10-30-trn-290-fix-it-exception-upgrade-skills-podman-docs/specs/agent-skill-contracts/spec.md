# Spec Delta

## ADDED Requirements

### Requirement: Skills upgrade flow is referenced from ghostship-admin skill

The `ghostship-admin` skill file SHALL mention the `ghostship upgrade --skills` mechanism and direct operators to the upgrade documentation so that an agent following the admin skill can find the correct command after a ghostship version update without having to leave the skill file or search the repository.

#### Scenario: Admin skill covers the upgrade path

- **WHEN** an agent reads `ghostship-admin/SKILL.md` looking for how to update skills after a new ghostship release
- **THEN** the file contains a reference to `ghostship upgrade --skills` and states that it rebuilds images and refreshes skill symlinks

#### Scenario: Admin skill does not reproduce the full upgrade docs inline

- **WHEN** an agent reads the upgrade reference in `ghostship-admin/SKILL.md`
- **THEN** the skill provides the command and points to the upgrade documentation for full details, rather than reproducing the entire upgrade procedure inline

