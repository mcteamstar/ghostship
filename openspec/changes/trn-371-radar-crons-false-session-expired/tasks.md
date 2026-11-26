# Tasks

## 1. Response classification

- [ ] 1.1 In `radar/web/src/api/request.ts`, report session-expired only for an opaque redirect, a redirected response or a `text/html` response, and report any other non-JSON response as an `http-error`. Verify new cases in `radar/web/test/api/request.test.ts`: login redirect and HTML 200 give `session-expired`; empty 200 with no content type, and a 200 with another content type, give `http-error`; a JSON 200 still parses. Run Vitest and typecheck.

## 2. Scheduled jobs gating

- [ ] 2.1 In `radar/web/src/detail/useCrewDetail.ts` and the Scheduled jobs section, request scheduled jobs only for a running crew with a non-empty `dashboard_url`, and render the section only then. Verify detail tests: a headless running crew sends no crons request, shows no Scheduled jobs section and shows no "Session expired" text; a dashboard crew whose request fails shows "Scheduled jobs unavailable."; a dashboard crew that succeeds lists its jobs or "No scheduled jobs."; a failed crons request leaves the agents and mailbox sections unchanged. Run Vitest and typecheck.

## 3. Docs

- [ ] 3.1 Update `docs/radar.md` (the Scheduled jobs line, the per-section state paragraph and the session-expired wording) and add an Unreleased entry to `CHANGELOG.md`. Update the Radar docs-parity test so it covers the new statements. Verify the docs-parity tests pass and fail when a documented sentence is deliberately broken.

## 4. Verification on a live fleet

- [ ] 4.1 Operator: run `ghostship upgrade`, open Radar through Caddy against a fleet with a running headless crew, and expand it. Verify it shows no Scheduled jobs section and no "Session expired" text, and that the agents, Captain and mailbox sections still load. If a running crew with a dashboard is available, verify its Scheduled jobs section shows its jobs or the unavailable line.

## Workflow follow-up

- Archive the change after review requirements are satisfied, and verify the archived result.
