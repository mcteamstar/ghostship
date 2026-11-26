# Tasks

## 1. Frontend toolchain and image build

- [ ] 1.1 Create `radar/web/` with React, TypeScript, Vite (`base: "/static/"`), Vitest and Testing Library, plus a committed lockfile. Verify `npm ci && npm run build && npm test` succeeds and the build emits `index.html` and hashed files under `assets/`.
- [ ] 1.2 Make `radar/Containerfile` multi-stage: a pinned Node stage runs `npm ci`, the type check and the build (no tests); the Python stage copies only the built output to `/app/static/`. Verify `podman build radar/` succeeds, the runtime image has no `node` binary or `node_modules`, and a deliberate type error fails the build.
- [ ] 1.3 Wire the build into install: confirm `_build_images` in `bin/lib/install_main.py` builds the new Containerfile for both `./install.sh` and `ghostship upgrade`, and report a clear "Radar bundle build failed" message that leaves the existing `ga-radar:latest` in place. Verify with an installer test (fake Podman) for the failure message, and a real `./install.sh` run on a host without Node.
- [ ] 1.4 Add a Node setup step and the frontend test and type-check commands to `.github/workflows/test.yml`. Verify the workflow YAML parses and the job runs the commands.
- [ ] 1.5 Add the new npm packages and the Node build image to `dependencies.yaml`. Verify `python3 scripts/dependency_check.py validate` passes.

## 2. Server changes

- [ ] 2.1 Update `radar/server.py`: `no-cache` for `/` and non-hashed files, `immutable` long-lived caching for `/static/assets/*`, and 404 (never `index.html`) for unknown `/api/` and `/static/` paths. Verify with updated unit tests in `tests/unit/test_radar_server.py` using a fixture `static/` directory, including the removed-module 404 scenarios.
- [ ] 2.2 Confirm the API proxy routes and health endpoint are unchanged. Verify the existing proxy and mail-subjects tests pass without edits to their assertions.

## 3. Data layer and shell

- [ ] 3.1 Add typed models for the fleet, agents, crons and mail-subjects payloads and the fetch wrapper that classifies `session-expired`, `transport-unreachable`, `network` and `http-error`. Verify unit tests cover a login redirect, non-JSON 200, 502/503/504, a thrown network error and a good response.
- [ ] 3.2 Implement the `useFleet` hook: five-second polling, 25-second auto-pause while any detail is open, last-good data, and stale (15 s) and critical (30 s) derivation. Verify with fake-timer tests for each scenario in `radar-ui` "UI state survives fleet polling" and "Loading, empty, error and stale states".
- [ ] 3.3 Build the app shell, theme tokens (light and dark by `prefers-color-scheme`) and the status banner with `role="status"`/`role="alert"`. Verify component tests for the loading, error, stale and session-expired ("Session expired, sign in again" with a login link) states.

## 4. Fleet view

- [ ] 4.1 Implement the fleet summary (running and stopped counts, active against maximum crews, free memory, omitted when absent). Verify component tests for present and absent capacity data.
- [ ] 4.2 Implement the fleet table with running and inactive sections, newest-first default ordering with invalid dates last, Last Task sort, Captain badges with staleness, stopped-crew gateway-warning rule and the dashboard link. Verify tests ported from the ordering, gateway-warning and Captain scenarios in `transport/radar` and `radar-ui`.
- [ ] 4.3 Implement the always-visible filter (crew ID and comp, case-insensitive) with the "no crews match" state. Verify a test with three crews showing the filter, a matching filter and a non-matching filter.
- [ ] 4.4 Implement the responsive layout (stacked card rows under 640 px, no horizontal page scroll at 360 px). Verify with a browser pass at 360, 768 and 1280 px and a recorded screenshot set.

## 5. Crew detail

- [ ] 5.1 Implement the per-row expand control (`<button aria-expanded>`), the `#crew=<id>` deep link, and per-row state that survives polls. Verify tests that an open row keeps its content and sends no new detail request when a fleet refresh arrives, and that the deep link opens the right crew.
- [ ] 5.2 Implement the agents, crons and mailbox-subjects sections with their loading, empty and unavailable states, session-expired handling and no partial mailbox lists. Verify tests ported from the mailbox-subject scenarios, including the single unavailable state and the empty-mailbox state.
- [ ] 5.3 Implement copy-crew-ID as a keyboard-reachable control that does not toggle the row. Verify tests for mouse and keyboard activation and the confirmation state.
- [ ] 5.4 Run an accessibility pass: accessible names, focus order, live-region announcements and AA contrast in both themes. Verify with `axe` in component tests (no violations) and a manual keyboard-only walkthrough.

## 6. Cutover, tests and docs

- [ ] 6.1 Remove `radar/static/*.js`, `index.html` and `style.css` and the legacy references in tests. Verify `git grep` finds no reference to the removed modules and the full Python unit suite passes.
- [ ] 6.2 Move the docs-parity tests and any test that reads Radar UI source to the new layout, keeping their assertions about behavior. Verify they pass and still fail when the documented UI behavior is deliberately broken.
- [ ] 6.3 Update `docs/radar.md` (UI behavior, themes, layout, session-expired state, build and dev loop), `CONTRIBUTING.md` (frontend commands and a dev proxy against a running fleet) and `CHANGELOG.md`. Verify the docs-parity tests pass and every documented command runs as written.
- [ ] 6.4 Integration check: build and start `ga-radar`, load it through Caddy against a running fleet, and walk the `radar-ui` scenarios (poll, open detail across a poll, filter, deep link, session expiry, dark mode, 360 px width). Verify `GET /static/main.js` returns 404, `GET /` returns `no-cache`, a hashed asset returns `immutable`, and the existing Caddy routes needed no change.

## Workflow follow-up

- Sequence this change after TRN-367 merges, then port its Refresh auth button and session-expiry display.
- Archive the change after review requirements are satisfied, and verify the archived result.
