# Tasks

## 1. Frontend toolchain and image build

- [x] 1.1 Create `radar/web/` with an `engines`/`.nvmrc` pin to Node 26, React, TypeScript, Vite (`base: "/static/"`), Vitest and Testing Library, plus a committed lockfile. Verify `npm ci && npm run build && npm test` succeeds and the build emits `index.html` and hashed files under `assets/`.
- [ ] 1.2 Make `radar/Containerfile` multi-stage: a Node 26 LTS stage (`node:26-alpine`, pinned by digest) runs `npm ci`, the type check and the build (no tests); the Python stage copies only the built output to `/app/static/`. Verify `podman build radar/` succeeds, the runtime image has no `node` binary or `node_modules`, the built `index.html` contains no inline `<script>`, and a deliberate type error fails the build.
- [ ] 1.3 Wire the build into install: confirm `_build_images` in `bin/lib/install_main.py` builds the new Containerfile for both `./install.sh` and `ghostship upgrade`, and report a clear "Radar bundle build failed" message that leaves the existing `ga-radar:latest` in place. Verify with an installer test (fake Podman) for the failure message, and a real `./install.sh` run on a host without Node.
- [ ] 1.4 Add a Node setup step and the frontend test and type-check commands to `.github/workflows/test.yml`. Verify the workflow YAML parses and the job runs the commands.
- [x] 1.5 Add the new npm packages and the Node build image to `dependencies.yaml`. Verify `python3 scripts/dependency_check.py validate` passes.

## 2. Server changes

- [x] 2.1 Update `radar/server.py`: `no-cache` for `/` and non-hashed files, `immutable` long-lived caching for `/static/assets/*`, and 404 (never `index.html`) for unknown `/api/` and `/static/` paths. Verify with updated unit tests in `tests/unit/test_radar_server.py` using a fixture `static/` directory, including the removed-module 404 scenarios.
- [x] 2.2 Confirm the API proxy routes, the health endpoint and TRN-367's `POST /api/crews/{crew_id}/auth/refresh` route with its same-origin check are unchanged. Verify the existing server-side tests in `tests/unit/test_radar_server.py` (proxy routes, health, the refresh route and its same-origin check) pass without edits to their assertions. The Node-driven client tests are replaced in 4.4 and 4.6, not kept.

## 3. Data layer

- [x] 3.1 Add typed models for the fleet, agents, crons and mail-subjects payloads and the fetch wrapper that classifies `session-expired`, `transport-unreachable`, `network` and `http-error`. Verify unit tests cover a login redirect, non-JSON 200, 502/503/504, a thrown network error and a good response.
- [x] 3.2 Implement the `useFleet` hook: five-second polling, 25-second auto-pause while any detail is open, last-good data, and stale (15 s) and critical (30 s) derivation. Verify with fake-timer tests for each scenario in `radar-ui` "UI state survives fleet polling" and "Loading, empty, error and stale states".

## 4. Parity port (same behavior as today)

Goal of this group: the React UI does what the current UI does, with the current look. New design work waits for group 6.

- [x] 4.1 Build the app shell with the existing visual style carried over from `style.css`: header, status line ("Refreshed at", error, stale classes), capacity text, the "Fleet Radar (N running)" page title and the empty and error rows. Verify component tests for the title, the refreshed-at text, and the loading, error, stale and empty states.
- [x] 4.2 Implement the fleet table with running and inactive sections, newest-first default ordering with invalid dates last, Last Task sort, Captain badges with staleness, the stopped-crew gateway-warning rule, the dashboard link and the existing filter that appears above 8 crews. Verify tests ported from the ordering, gateway-warning and Captain scenarios in `transport/radar`.
- [x] 4.3 Implement the per-row expand control, the `#crew=<id>` deep link, and per-row state that survives polls. Verify tests that an open row keeps its content and sends no new detail request when a fleet refresh arrives, and that the deep link opens the right crew.
- [x] 4.4 Implement the agents, crons and mailbox-subject sections with today's behavior: agents and crons stay silent on failure, mailbox subjects show the single unavailable state and never a partial list. Verify Vitest tests that carry over every assertion of `tests/unit/test_radar_mail_subjects_client.py`, then delete that Python test (it runs the removed `render.js` under Node).
- [x] 4.5 Implement copy-crew-ID that does not toggle the row. Verify tests for the click and the confirmation state.
- [x] 4.6 Port the Refresh auth action from TRN-367: the Credentials section and button, the six fixed outcomes, the unknown-result state, the session-expired, rejected, transport and network failure messages, `redirect: "manual"` handling, and the one-request-at-a-time rule that survives polls. Verify Vitest tests that carry over every assertion of `tests/unit/test_radar_auth_refresh_client.py` (request shape with `redirect: "manual"`, no body or headers, escaped guidance, no extra response fields drawn, one request at a time including after a poll re-render, session-expired and failure messages), including that a hostile response cannot inject markup or a CSS class, then delete that Python test.

## 5. Parity cutover

- [x] 5.1 Remove `radar/static/*.js`, `index.html` and `style.css`, and the static-asset assertions in `tests/unit/test_radar_server.py` for `main.js`, `render.js` and `app.js`. Verify `git grep` finds no reference to the removed modules, the new asset and 404 assertions from 2.1 pass, and the full Python unit suite passes.
- [x] 5.2 Move the docs-parity tests, including `test_auth_refresh_docs.py`, to the new layout, keeping their assertions about behavior. Verify they pass and still fail when the documented UI behavior is deliberately broken.
- [ ] 5.3 Document the build and dev loop in `CONTRIBUTING.md` (frontend commands and a dev proxy against a running fleet) and update `docs/radar.md` where it names the old modules. Verify the docs-parity tests pass and every documented command runs as written.
- [ ] 5.4 Parity checkpoint: build and start `ga-radar` through Caddy against a running fleet and walk the old and new UI side by side (fleet table, sections, sort, filter, expand, deep link, copy, Refresh auth, session expiry). Verify no behavior differs from the `radar-ui` "Radar preserves existing fleet behavior" and Refresh auth requirements, and list every field the old detail shows so group 6 can check none is lost, and record any difference as a defect before group 6 starts.

## 6. UI uplift

- [x] 6.1 Introduce design tokens and the light and dark themes by `prefers-color-scheme`. Verify a component test that both token sets load, and a real-browser contrast check of text and status colours in both themes with the results recorded.
- [x] 6.2 Implement the fleet summary (running and stopped counts, active against maximum crews, free memory, omitted when absent). Verify component tests for present and absent capacity data.
- [x] 6.3 Make the filter always visible (crew ID and comp, case-insensitive) with the "no crews match" state. Verify a test with three crews showing the filter, a matching filter and a non-matching filter.
- [x] 6.4 Implement the responsive layout (stacked card rows under 640 px, no horizontal page scroll at 360 px). Verify with a browser pass at 360, 768 and 1280 px and a recorded screenshot set.
- [x] 6.5 Redesign the crew detail agent view: running and finished groups with counts, one card per task showing agent, short ID, done state and elapsed, a persona accent for the six known agents and a neutral card for unknown ones, finished tasks collapsible by keyboard and pointer, and "No active tasks." for an empty running group. Verify component tests for a mixed list, the collapsed and expanded finished group, an empty agent name and the empty state, and that every task from the payload remains reachable.
- [x] 6.6 Redesign the mailbox history view: one section per mailbox in today's order with name and count, wrapped full subjects, `No messages.` for empty mailboxes and a single unavailable state on failure. Verify component tests for counts, a 200-character subject, an empty mailbox and the failure state, and that no field beyond mailbox name and subject is rendered.
- [x] 6.7 Add the explicit load states: a loading state for first load and for each detail section, an "unavailable" state when the agents or crons request fails (a failed section is never shown as empty), and the "Session expired, sign in again" state with a login link for fleet and detail requests. Verify component tests for each state, including that one failed section leaves the others unchanged.
- [ ] 6.8 Run an accessibility pass: accessible names, focus order, `aria-expanded` on the expand control, keyboard access to copy, sort, filter and links, and live-region announcements. Verify with `axe` in component tests for names, roles and labels (no violations; jsdom cannot measure colour contrast) and a manual keyboard-only walkthrough.
- [x] 6.9 Update `docs/radar.md` (themes, summary, always-visible filter, layout, agent and mailbox views, load and session-expired states) and `CHANGELOG.md`. Verify the docs-parity tests cover the new statements and every documented behavior matches the UI.

## 7. Integration

- [ ] 7.1 Final integration check: build and start `ga-radar`, load it through Caddy against a running fleet, and walk the `radar-ui` scenarios (poll, open detail across a poll, filter, deep link, session expiry, dark mode, 360 px width). Verify `GET /static/main.js` returns 404, `GET /` returns `no-cache`, a hashed asset returns `immutable`, and the existing Caddy routes needed no change.

## Workflow follow-up

- Archive the change after review requirements are satisfied, and verify the archived result.
- Review follow-up (no checkbox changed): the Refresh auth timeout (server bound 60 s, browser 75 s, "Still working…" note at 10 s) was added after the review in design.md decision 4 and the radar-ui delta. Operator steps for tasks 1.2, 1.3, 1.4, 5.3, 5.4, 6.8 and 7.1 are in evidence/operator-verification.md.
