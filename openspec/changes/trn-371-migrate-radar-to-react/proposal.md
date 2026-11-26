# Proposal

## Why

Radar started as a single table and is now outgrowing a hand-written HTML page. `radar/static/render.js` builds rows by concatenating HTML strings, and shared state lives in module-level singletons (`state.js`). Each new feature has to patch around full-table re-renders: open rows, expanded-detail caches, the filter box and in-flight requests must survive the 5-second poll. TRN-367 adds a stateful action button (Refresh auth) and a session-expiry path to the same page, so these costs keep growing. The poller also fails badly on session expiry: it follows the login redirect and shows `Fetch error: Unexpected token '<'`. A component model with declared state removes the whole class of "re-render wiped my UI" bugs and makes the UI testable. This is also the right moment for a visual and interaction uplift, because every view is being rewritten anyway.

## What Changes

- Rewrite the Radar SPA in React, built with a bundler at image build time. The source lives in the repository; the runtime image serves only the built output.
- Preserve every existing user-visible behavior: fleet table, running and inactive sections, default newest-first ordering, Last Task sort, expandable crew detail (agents, crons, mailbox subjects), Captain badges and staleness, gateway warnings, copy crew ID, `#crew=<id>` deep link, five-second polling with auto-pause while a row is open.
- Uplift the UI as part of the rewrite:
  - A fleet summary header (running, stopped, capacity, memory).
  - A crew filter that is always available, not only above 8 crews.
  - Light and dark themes that follow the system preference.
  - A responsive layout for narrow screens.
  - Keyboard and screen-reader access for row expansion and actions.
  - Explicit loading, empty, error and stale states.
  - A clear "session expired, sign in again" state (replaces the `Unexpected token '<'` failure).
- Change how `ga-radar` is built and served: a multi-stage image build compiles the app; assets are content-hashed; `index.html` is always revalidated.
- Keep the browser-facing API, Caddy routes, session gating and transport contract unchanged.
- Add frontend test tooling (component tests) and run it in CI. Track the new npm dependencies in `dependencies.yaml`.
- **BREAKING (internal only)**: `radar/static/*.js` ES modules and the `/static/main.js` entry point are removed. No external consumer is known; only the Radar tests and `docs/radar.md` reference them.

## Capabilities

### New Capabilities
- `transport/radar-ui`: Observable behavior of the Radar browser UI: fleet view, filtering, expansion, deep links, refresh and staleness states, session-expiry handling, themes, responsive layout and accessibility.

### Modified Capabilities
- `transport/radar`: The SPA is delivered as a built, content-hashed bundle under `/static/` instead of baked ES modules, with cache policy to match. The image build gains a frontend build stage. Fleet API, health, transport secret and Caddy route requirements keep their behavior.

## Impact

- Code: `radar/static/*` replaced by a frontend source tree (for example `radar/web/`); `radar/Containerfile` becomes multi-stage; `radar/server.py` cache headers and index handling.
- Tests: `tests/unit/test_radar_server.py` (static-asset assertions) and the Radar docs-parity tests move to the new layout; new frontend component tests run in `.github/workflows/test.yml`.
- Docs: `docs/radar.md`, `CONTRIBUTING.md` (frontend dev loop), `CHANGELOG.md`.
- Dependencies: Node toolchain at image build time only, run inside `podman build` by `./install.sh` and `ghostship upgrade`; no Node on the host or in the runtime image. React, a bundler and a test runner added to `dependencies.yaml`. The `ga-radar` build fetches npm packages, as the installer already does for pip, base images and the crew toolchains.
- Interactions: overlaps with TRN-367 (Refresh auth button and session-expiry display in Radar). This change assumes TRN-367 merges first and ports its behavior; if the order flips, the TRN-367 UI work must be carried into the React tree.
- Not affected: transport endpoints, Caddy config, `ga-radar` networking and the transport shared secret.
