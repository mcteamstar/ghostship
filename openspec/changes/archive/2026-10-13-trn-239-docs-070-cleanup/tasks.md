# Tasks

## 1. Fix agents.md tool-set table

- [x] 1.1 Update the tool-set claim on line 16 of `docs/agents.md`.

## 2. Replace deprecated env var names in architecture.md

- [x] 2.1 In `docs/architecture.md`, replace all references to `GA_AGENT_BACKENDS` and `GA_CREW_ACP_BACKEND` with `GA_CREW_AGENT`.

## 3. Replace deprecated env var names in auth.md

- [x] 3.1 In `docs/auth.md`, replace all references to `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS` with `GA_CREW_AGENT`.

## 4. Fix configuration.md Dockerfile example

- [x] 4.1 In `docs/configuration.md`, replace the "Extending the crew image" Dockerfile example.

## 5. Integration check

- [x] 5.1 Run `grep -rn "GA_AGENT_BACKENDS\|GA_CREW_ACP_BACKEND" docs/` and confirm no remaining unintentional references exist in the updated files. Run `tests/run.sh --unit` to confirm no regressions.

## Workflow follow-up

- Archive the change after review.
