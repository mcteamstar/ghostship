# Design

## Context

Radar today is about 1,100 lines of vanilla JavaScript served as static files by a small Starlette app (`radar/server.py`). `render.js` writes HTML strings into the table body, and `state.js` holds module-level singletons (open rows, detail cache, last data, sort). The image is Python-only (`radar/Containerfile`, build context `radar/`, built by `bin/lib/install_main.py`). Caddy routes `GET /`, `/api/crews*` and `/static/*` to `ga-radar:8080`. See proposal.md for motivation and scope.

## Goals / Non-Goals

**Goals:**
- Same data, same API, same URLs; operators see the existing behavior plus the uplift in `radar-ui`.
- A component model where a fleet poll cannot discard UI state by construction.
- No Node in the runtime image; reproducible, lockfile-pinned builds.

**Non-Goals:**
- No change to the transport API, Caddy routes, session auth or the `ga-radar` network placement.
- No client-side routing, server-side rendering or state-management library.
- No new data on screen beyond what the fleet, agents and mail-subjects endpoints already return.

## Decisions

**1. React 19 with TypeScript, built by Vite.**
Vite gives a fast dev loop and a plain static output with content-hashed filenames. TypeScript types the fleet payload once (`Crew`, `Captain`, `Agent`), which replaces the implicit shapes `render.js` reads today.
Alternatives: Preact (smaller bundle, but the request is for React and tooling parity matters more than a few tens of KB on an internal tool); Next.js or Remix (a server runtime we do not want); staying vanilla with lit-html (fixes string-building but not state ownership).

**2. Keep `/static/` as the asset base.**
Vite `base: "/static/"` puts assets at `/static/assets/<name>-<hash>.js` and `index.html` at the root of the output. The output is copied to `/app/static/`, so `server.py` keeps serving `static/index.html` at `/` and Caddy's `/static/*` route is untouched. No Caddy or install change.

**3. State lives in components, not singletons.**
- One `useFleet` hook owns polling: the five-second interval, the 25-second auto-pause while any detail is open, the last good data, the last success time and the error kind.
- Each crew row is a keyed component that owns its own expanded flag and its detail data (agents, crons, mail subjects). A fleet refresh re-renders props but does not unmount the row, so open state and loaded detail survive without a cache.
- The Refresh auth request state (in flight, last outcome) is also per-row state, so the disabled button and the outcome survive polls without the old `authRefreshing` set and detail cache. Collapsing a row drops it, as today.
- Filter and sort are top-level state, so a refresh never touches them.
- The "stale after 15 s, critical after 30 s" indicators derive from the last success time on a one-second tick.
Alternative: a store such as Zustand or Redux. Rejected: the state is small and tree-shaped, and the dependency adds review cost under `dependencies.yaml`.

**4. A small typed fetch wrapper classifies failures.**
It requests with `credentials: "include"` and `redirect: "manual"`. An opaque redirect, or a 200 with a non-JSON content type, is `session-expired`. 502/503/504 is `transport-unreachable`. A thrown `TypeError` is `network`. Everything else is `http-error`. Fleet, detail and refresh requests share it, which fixes the `Unexpected token '<'` failure in all three. The refresh `POST` keeps TRN-367's behavior: no body, `redirect: "manual"`, an opaque redirect or HTML 200 means session expired, and the outcome label and tone come from a fixed table so a response cannot choose markup or a CSS class.

**5. Plain CSS with custom properties.**
Design tokens (colour, spacing, radius, type scale) live in CSS variables; `prefers-color-scheme` swaps the token set, and a `matchMedia` listener is unnecessary because CSS handles it. No UI kit or Tailwind: the surface is one table plus detail panels, and a kit adds a large dependency for little gain. Layout uses a CSS grid that collapses table columns into stacked card rows under 640 px. Row expansion uses a real `<button aria-expanded>`; the error banner uses `role="status"` (stale) or `role="alert"` (failure).

**6. Build in a Containerfile stage, as part of install.**
The installer already builds `ga-radar` with `podman build <repo>/radar` in `_build_images`, which both `./install.sh` and `ghostship upgrade` run. A multi-stage `radar/Containerfile` therefore compiles the bundle during install with no new installer logic and no Node on the host. The Node stage (`node:<pinned>`) runs `npm ci`, `tsc --noEmit` and `vite build`; the Python stage copies only `dist/` to `/app/static/`. Source goes in `radar/web/`; `radar/static/` is removed.
- Component tests do **not** run in the image build. They run in CI. A test flake must not be able to fail an operator's install or upgrade; the type check and the bundle build still fail the image if the source is broken.
- If the build cannot fetch packages, the installer reports that the Radar bundle build failed because the npm registry was unreachable, names the build step, and stops. The existing `ga-radar:latest` image is not replaced on failure, so `ghostship upgrade` leaves the running Radar untouched.
- Client-only installs build no images and are unaffected.
Alternative: build `dist/` on the host and commit it. Rejected: committed build output drifts from source and bloats review diffs. Alternative: build on the host with a Node prerequisite. Rejected: it adds a host prerequisite to a Podman-only install.

**7. Cache policy by file kind.**
`server.py` sends `no-cache` for `/` and any non-hashed static file, and `public, max-age=31536000, immutable` for files under `/static/assets/`. This replaces the blanket revalidation that existed because ES modules had no hashes. Unknown `/api/` and `/static/` paths return 404 and never fall back to `index.html`.

**8. Tests at three levels.**
- Vitest and Testing Library for components and hooks, with fake timers for polling, auto-pause and staleness.
- The existing Python server tests, adapted to a fixture `static/` directory, for headers, 404s and proxying.
- Parity: a checklist mapped to `radar-ui` scenarios; the TRN-367 and TRN-370 docs-parity tests move to the new source layout and keep asserting the same behavior.
CI gets a Node setup step and runs the frontend tests and type check next to the Python unit job.

**9. Big-bang swap, no feature flag.**
The app is small and has one deployment target. The old and new UIs would have to share one route (`/`), so a flag would need server-side switching for little benefit. Rollback is the previous image (`ghostship upgrade` from the prior release).

## Risks / Trade-offs

- **Image builds now fetch npm packages.** This is the same network access the installer already needs for pip, base images and the crew toolchains → committed `package-lock.json` and `npm ci` for reproducible installs.
- **Supply-chain surface grows** (React, Vite, test tooling and transitive packages) → exact pins in the lockfile, entries in `dependencies.yaml`, `npm audit` in the review process, no runtime Node.
- **Regression in polling behavior** (auto-pause, staleness, deep link) → each behavior is a `radar-ui` scenario with a test; a manual parity pass against the old UI before merge.
- **Porting TRN-367's Refresh auth UI** (merged) → carry over its six outcomes, failure texts and one-request-at-a-time rule with equivalent component tests; the `POST` route, same-origin check and Caddy gating stay as they are.
- **Uplift scope creep** → the uplift is limited to the `radar-ui` requirements; further visual work becomes a separate change.
- **Bundle size** grows from about 25 KB of JS to roughly 150 KB gzip → acceptable on an internal, cached, hashed bundle.

## Migration Plan

1. Land the frontend toolchain and an empty app that builds in the image, with CI wired.
2. Port views in order: data layer, fleet table, detail panels, then the uplift items.
3. Switch `server.py` and the Containerfile to the built output; delete `radar/static/*.js`.
4. Move docs and parity tests; run the manual parity checklist in a browser against a running fleet.
5. Release through the normal `ghostship upgrade`. Rollback: reinstall the previous release image; no data or API migration is involved.

## Open Questions

- Exact visual design (palette, density, icon set). The `radar-ui` requirements fix behavior; visuals are reviewed on screenshots during implementation.
- The Node base image tag and digest pin, to be chosen against the `dependencies.yaml` image policy when the Containerfile stage is written.
