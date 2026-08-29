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

- [ ] 2.1 Decide whether `ghostship-capability` should be included in `plugin.json`
  by default or as an opt-in. Add it to the skills array in plugin.json once decided.

- [ ] 2.2 Update README — mention all three skills (admin, command, capability)
  and their scope in the "Connecting to a harness" or install section.

- [ ] 2.3 Review `ghostship-capability` for completeness — read it as a new user
  and check the new-composition and MCP catalogue sections are correct and
  sufficient to follow without the docs.

- [ ] 2.4 Consider whether `ghostship-admin` should reference `ghostship-capability`
  for post-install customisation, and `ghostship-command` should reference it
  for when an agent wants to add a new MCP server mid-operation.
