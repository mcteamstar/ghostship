# Design

## Context

The new Radar UI reads every JSON endpoint through `readJsonResponse` in `radar/web/src/api/request.ts`. Fetches use `redirect: "manual"`, so a redirect to the login page arrives as an opaque response, and that case is correctly a session expiry. The same function also calls any 200 whose `content-type` lacks `application/json` a session expiry, intended to catch the login page served in place of data.

The scheduled-jobs request goes to `/crews/<id>/api/crons`. The generated Caddy config has no route that matches `/crews/*/api/*` (checked in the installed `initial-config.json` and in `bin/lib/caddy_install.py`; the routes are `/mcp*`, `/files/*`, `/crews/*/dashboard`, the Radar paths and the misc route). Caddy therefore answers with an empty 200 for every crew, which today's wrapper reads as "session expired". See proposal.md.

## Goals / Non-Goals

**Goals:**
- Session expiry is reported only when the evidence says so.
- Radar stops depending on a route that does not exist.

**Non-Goals:**
- No new Radar or transport endpoint for scheduled jobs.
- No Caddy change. Routing `/crews/*/api/*` through the portal would expose the crew gateway API, including spawn, and is out of scope.
- No change to the Captain block, which is read from the fleet payload.

## Decisions

**1. Classify by evidence, not by absence of JSON.**
Session expired = opaque redirect, `response.redirected`, or a response whose content type is `text/html`. Any other non-JSON response is an `http-error`, which sections render as "unavailable". The login page, which Caddy serves as HTML, still lands on session-expired.
Alternative: treat an empty 200 as "no data" silently. Rejected: it hides real failures behind a blank section.

**2. Remove the scheduled-jobs request and section.**
The data has no working route, and the old UI showed nothing for it in practice. Deleting the request, the `CronsSection` component and the `crons` state from `useCrewDetail` keeps what operators see and removes a request that can only fail. The crew detail keeps its image line, Active tasks, Captain, Credentials and Mailbox subjects sections.
Alternative: keep the section and show "unavailable". Rejected: every crew would show a permanent notice for a route that cannot work.
Alternative: add a `ga-radar` crons endpoint backed by a new transport internal route. Better long term and read-only, but a transport and Radar change with its own specs. Left as separate work.
Alternative: route `/crews/*/api/*` in Caddy as the `caddy-proxy` spec says. Rejected: security-sensitive and unrelated to Radar's needs.

**3. Tests prove the boundary.**
Wrapper tests cover redirect, HTML 200, empty 200, a 200 with an unrelated content type and a good JSON response. Detail tests assert no request to `/crews/<id>/api/crons`, no Scheduled jobs section and no session-expired text for a running crew, and that the agents, Captain, Credentials and mailbox sections are unchanged.

## Risks / Trade-offs

- [Someone relied on the Scheduled jobs section] → it never received data on a stock install, so nothing visible is lost. Restoring it needs the separate endpoint work.
- [Other non-JSON, non-HTML replies from the portal on session expiry] → today's login page is HTML. If that changes, non-redirect detection would need updating; the redirect case is unaffected.
- [Docs and specs still mention scheduled jobs elsewhere] → this change updates `radar-ui`, `docs/radar.md`, the changelog and the docs-parity test; the unrelated `caddy-proxy` spec drift is recorded in the proposal.

## Migration Plan

Ship with the next `ghostship upgrade`. Rollback is the previous image. No data or API migration is involved.
