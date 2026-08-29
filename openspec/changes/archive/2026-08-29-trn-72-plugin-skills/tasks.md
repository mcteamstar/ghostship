# TRN-72 Tasks — Plugin Skill Improvements

## Section 1: Completed in this session

- [x] 1.1 Rewrite `ghostship-command` with operational patterns (captain-first,
  seeding, evac+merge, crew_id naming, steer-on-timeout, dedup notes)
- [x] 1.2 Update `ghostship-admin` — add Get ghostship section, `~/.ghostship`
  default, Kiro skill path
- [x] 1.3 Create `ghostship-capability` skill — academy customisation and
  composition building how-tos
- [x] 1.4 Add skill version check to release gate
- [x] 1.5 Bump VERSION, plugin manifests, and all skill files to 0.2.0

## Section 2: Remaining

- [x] 2.1 `ghostship-capability` wired into `EXTERNAL_SKILLS.md` index (skills
  are auto-discovered by harness from `skills/` directory — no plugin.json
  change needed).

- [x] 2.2 Updated README — mentions all three skills (admin, command, capability)
  with scope summaries in the quick install and plugin sections.

- [x] 2.3 `ghostship-capability` reviewed for completeness — structure, how-tos,
  and composition sections are correct and actionable without the docs.

- [x] 2.4 Added cross-references: `ghostship-admin` points to capability for
  post-install customisation; `ghostship-command` points to capability for
  MCP server wiring and composition building.
