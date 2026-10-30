# Tasks

## 1. independent-review.md — privacy reviewer

- [ ] 1.1 Add 5th reviewer to `academy/orders/independent-review.md`: dispatch a Banshee with task prefix `REVIEW privacy <intent_id> <change?>`, expected mail subject `review privacy done <change?>`, with scan instructions covering the 7 privacy categories from the spec; verify the template renders without YAML/markdown errors
- [ ] 1.2 Update the wait-and-collect phase in `independent-review.md` to expect 5 reviewer reports (adding `review privacy done <change?>`) before consolidating; verify the template's expected-subjects list has 5 entries
- [ ] 1.3 Update the consolidation section in `independent-review.md` to include a **Privacy** section in the consolidated report structure; verify the template's consolidation instructions reference all 5 reviewers

## 2. independent-review.md — test-coverage sharding

- [ ] 2.1 Replace the single test-coverage Banshee dispatch in `independent-review.md` with 3 parallel dispatches (Shard A: `transport/`, Shard B: `tests/unit/`, Shard C: `tests/integration/` + other), each with distinct task prefix `REVIEW test-coverage-<shard> <intent_id> <change?>`; verify the 3 dispatches are structurally parallel (no sequential dependency between them)
- [ ] 2.2 Update the wait-and-collect phase to expect 3 test-coverage sub-reports (`review test-coverage-a done`, `review test-coverage-b done`, `review test-coverage-c done`) instead of 1; verify expected-subjects list is updated
- [ ] 2.3 Update the consolidation section to merge the 3 test-coverage sub-reports into a single **Test Coverage** section with shard attribution; verify consolidation instructions reference all 3 shards

## 3. privacy.md standalone template

- [ ] 3.1 Create `academy/orders/privacy.md` with front matter (`aliases: ["privacy-probe", "scrub"]`) and dispatch instructions: single Banshee with task prefix `PRIVACY PROBE <intent_id>`, full-codebase scan for the 7 privacy categories (explicitly excluding RFC-standard example domains and loopback addresses), self-contained report mailed to `raven@localhost` with subject `privacy probe complete`; verify file exists and has valid front matter
- [ ] 3.2 Add wait-and-collect and self-cancel phases to `privacy.md`: Raven waits for `privacy probe complete`, forwards to `admiral@localhost`, then self-cancels; verify template follows the same Raven check-in pattern as `free-will.md`

## 4. Skill and docs updates

- [ ] 4.1 Add `privacy` / `privacy-probe` / `scrub` to the Captain templates table in `.claude-plugin/skills/ghostship-command/SKILL.md` alongside `sdd`, `indy`, `free-will`; verify the table has 4 template entries
- [ ] 4.2 Update `docs/architecture.md` Captain supervision section to document the privacy probe template and note that indy now dispatches up to 7 concurrent agents (5 reviewers + test-coverage sharding); verify the section accurately reflects the new fan-out

## 5. Validation

- [ ] 5.1 Run `openspec validate` on the change and verify it passes with no errors
- [ ] 5.2 Deploy updated academy templates to corsair (`ghostship upgrade` or rsync `academy/orders/` to the data volume) and run a test indy on a small crew to verify 5 reviewer dispatches appear in crew tasks and Raven correctly waits for all reports before consolidating

## Workflow follow-up

- Archive the change after the release branch is cut and a live indy run confirms the privacy reviewer and test-coverage sharding work end-to-end.
