# Proposal

## Why

After the TRN-371 Radar rewrite reached a live fleet, the Scheduled jobs section of an open crew showed "Session expired, sign in again" on an install with no API key, where no session can expire. Two things combine:

1. Radar requests `/crews/<id>/api/crons`, but Caddy has no route for `/crews/*/api/*` in either install mode. Caddy answers that path itself with `200`, an empty body and no content type, for every crew. The transport has a `/crews/{id}/api/{path}` proxy, but nothing routes to it, so the old UI's Scheduled jobs section never received data on this deployment and stayed silent. (The `caddy-proxy` spec lists the route; the code never contained it.)
2. Radar's request wrapper treats any 200 whose content type is not JSON as an expired session, so that empty answer is shown as a session expiry with a sign-in link, on every running crew.

## What Changes

- Radar reports "session expired" only when a request was redirected to the login page or answered with an HTML page. An empty or otherwise non-JSON, non-HTML 200 is an ordinary request failure.
- Radar stops requesting scheduled jobs and removes the Scheduled jobs section from the crew detail, because the data has no working route. What operators see today (no jobs) stays the same, without the false notice.
- The docs, changelog and docs-parity test stop describing the section. Showing gateway jobs again needs a real Radar endpoint and is a separate piece of work.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `transport/radar-ui`: "Expired session is reported clearly" no longer counts an empty or other non-JSON response as a session expiry. "Radar preserves existing fleet behavior", "UI state survives fleet polling" and "Uplift changes presentation, not content" no longer include scheduled jobs. "Crew detail sections report load failures" is removed and replaced by "Agents and mailbox sections report load failures" (OpenSpec cannot drop a scenario from a modified requirement, so the requirement is renamed).

## Impact

- Code: `radar/web/src/api/request.ts`, `radar/web/src/api/endpoints.ts`, `radar/web/src/detail/useCrewDetail.ts`, the crew detail component and the Scheduled jobs section component (deleted), and their Vitest tests.
- Docs: `docs/radar.md`, `CHANGELOG.md`, the Radar docs-parity test.
- Not affected: the Radar server, Caddy routes, the transport API, the Captain block (it comes from the fleet payload) and the Refresh auth action.
- Known gap left open: the `caddy-proxy` spec lists `/crews/*/api/*` as routed, but no Caddy config does. Reconciling the spec with the code is not part of this change.
