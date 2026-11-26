# Tasks

## 1. Response classification

- [x] 1.1 In `radar/web/src/api/request.ts`, report session-expired only for an opaque redirect, a redirected response or a `text/html` response, and report any other non-JSON response as an `http-error`. Verify new cases in `radar/web/test/api/request.test.ts`: login redirect and HTML 200 give `session-expired`; empty 200 with no content type, and a 200 with another content type, give `http-error`; a JSON 200 still parses. Run Vitest and typecheck.

## 2. Remove the scheduled-jobs request

- [x] 2.1 Delete the crons request (`fetchCrons`, `cronsUrl`), the `crons` section state in `useCrewDetail`, the `CronsSection` component and its use in `CrewDetail`. Remove the crons types and fixtures that nothing else uses. Verify detail tests: a running crew sends no request to `/crews/<id>/api/crons`, shows no Scheduled jobs section and no "Session expired" text, and its agents, Captain, Credentials and mailbox sections behave as before; an open row still keeps its content across a fleet refresh. Run Vitest and typecheck, and confirm `git grep -i "crons"` finds no remaining references under `radar/web`.

## 3. Docs

- [x] 3.1 Update `docs/radar.md` (the section list, the per-section state paragraph and the session-expired wording) and add an Unreleased entry to `CHANGELOG.md`. Update the Radar docs-parity test (`tests/unit/test_radar_ui_docs.py`) so it no longer expects the Scheduled jobs strings and covers the new wording. Verify the docs-parity tests pass and fail when a documented sentence is deliberately broken; run the full Python unit suite.

## 4. Verification on a live fleet

- [ ] 4.1 Operator: run `ghostship upgrade`, open Radar through Caddy against a fleet with a running crew, and expand it. Verify there is no Scheduled jobs section and no "Session expired" text, that Active tasks, Captain, Credentials and Mailbox subjects still load, and that the browser shows no request to `/crews/<id>/api/crons`.

## Workflow follow-up

- Archive the change after review requirements are satisfied, and verify the archived result.
