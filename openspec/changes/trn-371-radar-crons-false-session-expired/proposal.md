# Proposal

## Why

After the TRN-371 Radar rewrite shipped to a live fleet, the Scheduled jobs section of an open crew showed "Session expired, sign in again" on a crew in an install with no API key, where no session can expire. The scheduled-jobs request goes to `/crews/<id>/api/crons`, a crew-dashboard route. For a crew without a dashboard, Caddy answers `200` with an empty body and no content type. Radar's request wrapper treats any 200 whose content type is not JSON as an expired session, so every headless crew shows a false session-expiry notice with a sign-in link. Most crews are headless. The old UI ignored a failed crons request and showed nothing.

## What Changes

- Radar reports "session expired" only when a request was redirected to the login page or answered with an HTML page. An empty or otherwise non-JSON, non-HTML 200 is an ordinary request failure.
- Radar does not request scheduled jobs for a crew that has no dashboard URL, and shows no Scheduled jobs section for it, which matches the old UI. A crew with a dashboard whose request fails still shows "Scheduled jobs unavailable."
- Correct the Radar docs and the docs-parity test that describe the session-expired state and the Scheduled jobs section.

## Capabilities

### New Capabilities
<!-- None. -->

### Modified Capabilities
- `transport/radar-ui`: "Expired session is reported clearly" no longer counts an empty or other non-JSON response as a session expiry. "Crew detail sections report load failures" excludes crews without a dashboard from the Scheduled jobs request and section.

## Impact

- Code: `radar/web/src/api/request.ts` (response classification), `radar/web/src/detail/useCrewDetail.ts` and the Scheduled jobs section component (dashboard gating), their Vitest tests.
- Docs: `docs/radar.md`, `CHANGELOG.md`, and the Radar docs-parity test.
- Not affected: the Radar server, Caddy routes, the transport API and the Refresh auth action.
- Open assumption: the crons route works for a crew that has a dashboard. It could not be confirmed live because the only crews with dashboard URLs are stopped. The change keeps the request for those crews and covers the failure case with "unavailable."
