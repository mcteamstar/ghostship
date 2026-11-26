# Design

## Context

The new Radar UI reads every JSON endpoint through `readJsonResponse` in `radar/web/src/api/request.ts`. Fetches use `redirect: "manual"`, so a redirect to the login page arrives as an opaque response, and that case is correctly a session expiry. The same function also calls any 200 whose `content-type` lacks `application/json` a session expiry, intended to catch the login page served in place of data.

The scheduled-jobs request goes to `/crews/<id>/api/crons`, a crew-dashboard route that Caddy handles, not `ga-radar`. For a crew without a dashboard, Caddy answers `200`, an empty body and no content type (verified with `curl` against five crews). Today's wrapper reads that as "session expired". See proposal.md for the symptom.

## Goals / Non-Goals

**Goals:**
- Session expiry is reported only when the evidence says so.
- A headless crew shows no Scheduled jobs section and sends no request for it, as in the old UI.

**Non-Goals:**
- No change to the Radar server, Caddy routes, the transport API or the Refresh auth action.
- No new Radar endpoint for scheduled jobs.

## Decisions

**1. Classify by evidence, not by absence of JSON.**
Session expired = opaque redirect, `response.redirected`, or a response whose content type is `text/html`. Any other non-JSON response is an `http-error`, which the sections already render as "unavailable". The login page, which Caddy serves as HTML, still lands on session-expired.
Alternative: treat an empty 200 as "no data" silently. Rejected: it hides real failures behind a blank section.

**2. Gate the crons request on the crew's dashboard URL.**
`useCrewDetail` requests scheduled jobs only for a running crew with a non-empty `dashboard_url`, and the Scheduled jobs section renders only in that case. A crew with a dashboard whose request fails shows "Scheduled jobs unavailable."
Alternative: request for every running crew and show "unavailable" on failure. Rejected: nearly every headless crew would show an unavailable notice for a route that cannot exist for it.
Alternative: serve crons through a new `ga-radar` endpoint. Rejected: a transport and server change for a section the old UI hid in the same situation.

**3. Tests prove the boundary.**
Wrapper tests cover redirect, HTML 200, empty 200, a 200 with an unrelated content type and a good JSON response. Detail tests cover a headless crew (no request, no section, no notice), a dashboard crew that fails, and one that succeeds.

## Risks / Trade-offs

- [The crons route has not been confirmed for a live crew with a dashboard] → the request is kept for those crews and failures show as unavailable. Checking it needs a running crew started with a dashboard.
- [`dashboard_url` could be set for a crew whose dashboard is down] → the section shows "unavailable", which is accurate.
- [A different non-JSON response from Caddy on session expiry] → today's login page is HTML. If the portal changes it, session-expired detection for non-redirect cases would need updating; the redirect case is unaffected.

## Migration Plan

Ship with the next `ghostship upgrade`. Rollback is the previous image. No data or API migration is involved.
