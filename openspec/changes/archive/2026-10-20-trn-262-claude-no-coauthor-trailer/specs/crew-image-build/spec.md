## ADDED Requirements

### Requirement: Claude crews add no Claude Code attribution
A crew image built with the claude agent toolchain SHALL configure Claude Code, at the managed (system-wide) settings level, to add no attribution to commits or pull requests. The setting SHALL live outside the crew's home volume, so it applies to every crew launched from the image whatever that volume already contains, and SHALL take precedence over user, project and session settings. Images built without the claude toolchain SHALL NOT contain this setting.

#### Scenario: Claude crew commit has no co-author trailer
- **WHEN** an agent in a claude-backend crew commits through Claude Code
- **THEN** the commit message contains no `Co-Authored-By` trailer naming Claude

#### Scenario: Claude crew PR text has no attribution
- **WHEN** an agent in a claude-backend crew writes a pull request description through Claude Code
- **THEN** the description contains no "Generated with Claude Code" text

#### Scenario: Existing home volume does not hide the setting
- **WHEN** a claude crew is launched from a rebuilt image onto a home volume created by an earlier image, or its `~/.claude/` is replaced by credential injection
- **THEN** attribution is still disabled

#### Scenario: Session settings cannot re-enable attribution
- **WHEN** a session's project or local Claude Code settings are written at spawn time
- **THEN** attribution remains disabled

#### Scenario: Image without the claude toolchain is unchanged
- **WHEN** the crew image is built without the claude toolchain
- **THEN** it contains no Claude Code managed settings file

#### Scenario: Git identity is unaffected
- **WHEN** `crew.git.author.name` and `crew.git.author.email` are set or unset
- **THEN** commit author and committer identity behave as before; only the attribution text changes
