# TRN-72 — Plugin Skill Improvements

## Summary

Ghostship ships three plugin skills that guide agents through using the
system. After heavy operational use, the existing two skills needed significant
updates and a third needed to be created.

## Problems

### ghostship-command gaps
- Undersold captain: positioned as "opt-in autonomous mechanism" when it
  should be the default for any non-trivial work. A single dispatch has a
  60-min hard timeout and no recovery.
- Bundle seeding pattern was incomplete — showed `supply()` call but not
  the required `curl` POST, nor the `git bundle create` step.
- No evac+merge guidance — agents following the skill would download a
  bundle and not know what to do with it (git fetch, inspect, cherry-pick).
- crew_id naming had opinionated hardcoded conventions rather than a soft
  hierarchy reflecting real variety.
- No guidance on `steer`ing timed-out tasks vs fresh dispatch (steer
  preserves full session context; fresh dispatch loses it).
- Captain dedup/self-pause behaviour not documented.

### ghostship-admin gaps
- No "get ghostship" step — jumped straight to `./install.sh` without
  saying where to clone from or where to install to.
- Only mentioned Claude Code for skill wiring, not Kiro.
- No recommended install location for agent-driven installs.

### Missing: ghostship-capability
No skill existed for configuring what crews can do — adding agents, skills,
steering, orders, MCP servers, or building new compositions. This is a
distinct concern from installing (admin) or driving (command).

## Decisions

- **ghostship-command**: rewrite with operational patterns from real use.
  Captain-first framing, full seeding/evac patterns, crew_id soft hierarchy
  (repo > ticket > topic/verb-noun), steer-on-timeout guidance.
- **ghostship-admin**: add "Get ghostship" section, recommend `~/.ghostship`
  as default install location (clean home for future persistent data), add
  Kiro skill path.
- **ghostship-capability**: new skill. Covers academy curriculum
  customisation (agents, skills, steering, orders, MCP catalogue) and
  building new crew compositions. Action-oriented how-to format.
- **Release gate**: add skill version check alongside existing manifest
  check — all skill `version:` fields must match `VERSION`.
- **VERSION + manifests**: bumped to `0.2.0` to match the release branch.

## Completed scope

All items implemented:
- `ghostship-capability` auto-discovered via `skills/` directory (no plugin.json
  change needed); indexed in `EXTERNAL_SKILLS.md`.
- README updated to mention all three skills.
- Cross-references added between admin↔capability and command↔capability.
