# TRN-371 session-expired fix: live-check evidence

This file is the evidence for the Admiral's check 4: the bug reproduced before the fix and gone after. An agent cannot run the live fleet. The reproduction below runs the Radar UI in Vitest against the pre-fix source and the fixed source, with the same test code. The live-fleet check is operator task 4.1, recorded in `operator-verification.md`.

## Commits

- Reviewed commit: `38359c62`, "fix: stop false session-expired notices in Radar crew detail (TRN-371)".
- Pre-fix source: `81dbcf54`, the parent of `38359c62` before the fix.
- Review commits on `release/0.13.2`: `005594d0` adds two classifier test cases. The commit that adds this file and the other change artifacts follows it.

## Environment

- Radar tests ran on Node v24.22.3 (`/usr/bin/node`). The pinned runtime is Node 26 (`radar/web/.nvmrc` is `26`, and `engines` is `>=26 <27`). Node 26 is not installed on this host, and no version manager is present. The Node 26 run is deferred.
- Vitest 5.1.2 and `tsc` come from `radar/web/node_modules`. Python is 3.12.16 with the repository `.venv` (pytest 8.4.2).

## Check 1: classifier in `radar/web/src/api/request.ts`

At `38359c62`, `readJsonResponse` runs these checks in order:

1. An opaque redirect, or a response with `redirected` set, is `session-expired`.
2. Status 502, 503 or 504 is `transport-unreachable`.
3. Any other non-2xx status is `http-error`.
4. A `text/html` content type is `session-expired`.
5. Any other content type that is not `application/json` is `http-error` ("Non-JSON response").
6. A JSON body that does not parse is `http-error`.

Test result at `005594d0`: `radar/web/test/api/request.test.ts` passes 22 of 22 tests. The cases cover the opaque redirect, the followed redirect, a 200 login page with an HTML body, an empty 200 with no content type, a 200 with `text/plain`, and HTML error pages with status 404 and 500.

Interpretation: a non-2xx HTML page is an `http-error`, as it was before this change, and `refresh.ts` does the same. The Admiral's wording could also be read as every HTML response. That reading would show the sign-in note for a 500 error page, so the code keeps the status check first. `design.md` now states this rule.

Boundary check: in a scratch copy, moving the `text/html` branch above the status check fails the two new 404 and 500 cases with `expected 'session-expired' to be 'http-error'`. The cases therefore pin the boundary.

## Check 2: scheduled-jobs removal

- `git grep -n -i crons -- radar/web` at `005594d0`: no matches (exit 1).
- `git grep -n -i cron -- radar/web` at `005594d0`: no matches (exit 1).
- The Radar browser code makes four requests: `GET /api/crews`, `GET /api/crews/{id}/agents`, `GET /api/crews/{id}/mail-subjects`, and `POST /api/crews/{id}/auth/refresh`. The `ga-radar` Caddy route serves `/`, `/api/crews`, `/api/crews/*` and `/static/*`, so each request has a route.

## Check 3: docs, changelog and docs-parity test

- `docs/radar.md`, the Unreleased entries in `CHANGELOG.md`, and `tests/unit/test_radar_ui_docs.py` describe the removed section and the new classifier line.
- The docs-parity test on the pre-fix docs and UI (`81dbcf54`): 2 failed, 5 passed. The failures are `test_session_expiry_is_documented_as_the_request_wrapper_classifies_it` and `test_scheduled_jobs_section_is_gone_from_the_docs_and_the_ui`.
- The docs-parity test on the fixed tree: 7 passed.
- Deliberate breaks on the fixed tree, each in a scratch copy:
  - Removing "answered with HTTP 200 and an HTML page" from `docs/radar.md` fails `test_session_expiry_is_documented_as_the_request_wrapper_classifies_it`.
  - Changing "No active tasks." to "No tasks." in `AgentsSection.tsx` fails `test_documented_wording_is_what_the_ui_draws`.
  - Disabling the `text/html` branch in `request.ts` (its condition replaced by `false`) fails `test_session_expiry_is_documented_as_the_request_wrapper_classifies_it`.

## Check 4: the bug reproduced before the fix and gone after

The test below mirrors the field report. A running crew is listed, its row is expanded, and the crons path answers Caddy's empty 200 (status 200, no body, no content type). Before the fix, Radar sends the request and shows "Session expired, sign in again". After the fix, Radar sends no request under `/crews/` and shows no session-expired note.

Save this file as `radar/web/test/app/trn371-live-symptom.test.tsx` in a scratch copy. Do not add it to the checkout: it contains the crons path, which the Radar grep check rejects.

```tsx
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, type Mock } from "vitest";
import { App } from "../../src/App";
import { crew, fleet, jsonResponse, mailboxes, routeFetch } from "../support/fixtures";

// Live symptom (TRN-371): Caddy answers the unrouted /crews/<id>/api/crons path with an
// empty 200 that has no content type. A running crew's detail must not show a session
// expiry, and Radar must not send that request at all.
describe("TRN-371 live symptom: empty 200 on the crons path", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  it("running crew: no request under /crews/ and no session-expired note", async () => {
    const mock: Mock = routeFetch({
      "/api/crews": () => jsonResponse(fleet([crew({ crew_id: "alpha", status: "running" })])),
      "/api/crews/alpha/agents": () => jsonResponse({ agents: [] }),
      "/api/crews/alpha/mail-subjects": () => jsonResponse({ mailboxes: mailboxes({ ghost: ["Handoff"] }) }),
      "/crews/alpha/api/crons": () => new Response(null, { status: 200 }),
    });
    const { container } = render(<App />);
    await screen.findByText(/Refreshed at:/);
    fireEvent.click(container.querySelector('tr[data-crew-id="alpha"]') as HTMLElement);
    await waitFor(() => expect(screen.getByText("Handoff")).toBeInTheDocument());
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    const crewProxyCalls = mock.mock.calls.filter((call) => String(call[0]).startsWith("/crews/")).length;
    expect.soft(crewProxyCalls, "requests under /crews/").toBe(0);
    expect.soft(screen.queryByText("Session expired, sign in again"), "session-expired note").toBeNull();
  });
});
```

Procedure, with `REPO` set to the checkout and `S` set to an empty scratch directory:

```
mkdir -p "$S/pre" "$S/post"
git -C "$REPO" archive 81dbcf54 radar/web | tar -x -C "$S/pre"
git -C "$REPO" archive HEAD radar/web | tar -x -C "$S/post"
ln -s "$REPO/radar/web/node_modules" "$S/pre/radar/web/node_modules"
ln -s "$REPO/radar/web/node_modules" "$S/post/radar/web/node_modules"
# copy the test above into test/app/ of both trees, then in each tree:
cd "$S/<tree>/radar/web" && ./node_modules/.bin/vitest run test/app/trn371-live-symptom.test.tsx
```

Results:

| Source | Exit | Result |
|:-------|:-----|:-------|
| `81dbcf54` (before the fix) | 1 | Fails. `requests under /crews/: expected 1 to be +0`, and the note shows `Session expired, sign in again`. |
| `005594d0` (after the fix) | 0 | Passes. 1 of 1 test. |

The full Radar suite, run with the fixed tests against the pre-fix source, shows the bug as well. Of 205 tests, 6 fail on `81dbcf54`:

- `test/api/request.test.ts`: "reports an empty 200 with no content type as a failed request, not an expired session"; "reports a 200 with another content type as a failed request, not an expired session".
- `test/app/detail-states.test.tsx`: "shows an unavailable state, not a session expiry, when the agents request answers an empty 200".
- `test/app/expansion.test.tsx`: "keeps an open row open and sends no detail request when a fleet refresh arrives"; "shows no scheduled-jobs section and sends no request for one"; "requests live tasks once the crew is running, instead of waiting forever".

On the fixed tree, all 205 tests pass.

## Root cause, checked against the repository

`bin/lib/caddy_install.py` generates the Caddy routes for both install modes:

- Auth routes: `/mcp*`, `/files/*`, and `/crews/*/dashboard` (POST and DELETE).
- `ga-radar`: `/`, `/api/crews`, `/api/crews/*`, `/static/*`.
- Misc: `/health`, `/version`, `/openapi.json`, `/dashboard/*`, `/login`, `/login*`, `/logout`, `/logout*`, `/crews/*/captain/stop`.

No route matches `/crews/*/api/*`. The transport has a handler for that path (`transport/server.py`), but no Caddy route sends traffic to it. `git log -S 'crews/*/api' -- bin/lib/caddy_install.py` returns no commits, so the generator has never had such a route.

## Other checks

- `openspec validate trn-371-radar-crons-false-session-expired --strict`: valid.
- A scratch archive of the change, run on a copy of `openspec/` with `--yes`, merges without errors. `transport/fleet-overview` gets 1 modified requirement and 1 rename. `transport/radar-ui` gets 1 added, 4 modified and 1 removed requirement. The only warning is the open task 4.1.
- Full Python unit suite at `005594d0` (`./.venv/bin/python -m pytest tests/unit`): 2035 passed, 2 skipped.
- Typecheck (`tsc --noEmit`) at `005594d0`: exit 0.
- Vitest at `005594d0`: 17 files, 205 tests passed.

## Deferred

- Operator task 4.1 (live fleet, Caddy, browser): operator-only. See `operator-verification.md`. The Admiral ruled that it does not block review or archive.
- Node 26 run of the Radar suite (`npm run typecheck` and `npm test` in `radar/web`): not run. Node 26 is not on this host. The only npm route to it is a third-party wrapper package, which this review did not install. The pinned runtime should run the suite before the release.
