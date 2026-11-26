# Radar — Fleet Dashboard

Radar is the ghostship fleet observability dashboard. Opening `GET /` in a browser shows all crews, their status, active tasks, Captain state, and schedule — no MCP agent session required.

## Accessing Radar

Navigate to the transport URL in a browser:

```
http://localhost:64057/          # local dev (no API key)
https://your-portal-hostname/    # production (API key required)
```

When `GA_API_KEY` is set, you will be redirected to `/dashboard/login` first. Log in once; the `gs_session` cookie covers all subsequent dashboard and Radar requests in the same browser session.

## What it shows

| Column | Description |
|:-------|:------------|
| Crew | Crew ID with activity badges (see below) |
| Status | `running` (green glow) or `stopped` (dimmed row) |
| Backend | `kiro`, `claude`, or `codex` |
| Comp | e.g. `spec-ops` |
| Uptime | Running time for live crews; the creation date for stopped crews |
| Last Task | Relative time since last dispatch (e.g. `3m ago`) |
| Dashboard | Link to per-crew KC dashboard (when `dashboard=True` at launch) |

**Activity badges** on the crew name:
- `N active` (cyan) — the crew has N running agent tasks
- `⚑ captain` (purple) — an active Captain schedule is running
- `⚑ paused` (muted) — a Captain schedule exists but is paused

Click any row to expand per-crew detail. [Crew detail](#crew-detail) describes what the expanded panel shows.

The table polls `GET /api/crews` every 5 seconds. Open rows stay open across refreshes.

## Layout, summary and filter

Radar follows the system colour preference. It is light by default and switches to dark when the system asks for dark, without a reload. Text and status colours meet WCAG AA contrast in both themes.

Above the table, a summary shows the `Running` and `Stopped` counts. When the fleet reports them, it also shows `Capacity` (active crews against the maximum) and `Free memory`. A value the fleet does not report is left out.

The filter above the table is always shown. It matches crew ID and comp, ignoring case. When nothing matches, Radar shows `No crews match filter.`

Below 640 px, each crew becomes a card, and each value is labelled with its column name. The page does not scroll sideways at 360 px.

## Crew detail

Expanding a row shows, in order: the crew's image version, its active tasks, its Captain state, its credentials, and its mailbox subjects.

- **Active tasks** lists running tasks as cards under a `Running · N` heading. Finished tasks sit behind a `Finished · N` disclosure, which opens from the keyboard or the pointer. Each card shows the agent name, the short task ID, whether the task is running or done, and its elapsed time. The six persona agents each have an accent colour. Any other name is shown on a neutral card, and an empty name is labelled `unknown agent`. A running crew with no running tasks shows `No active tasks.`
- **Mailbox subjects** has one section per mailbox, in the order listed under [Mailbox subjects](#mailbox-subjects), with the mailbox name and its subject count. Long subjects wrap in full.

Each section shows its own state. While its request is pending, a section shows a loading line: `Loading tasks…` or `Loading mailbox subjects…`. If the agents or mailbox request fails, that section shows `Active tasks unavailable.` or `Mailbox subjects unavailable.`. A failed section never shows an empty list in its place. A request redirected to sign-in, or answered with HTTP 200 and an HTML page, shows `Session expired, sign in again`, with a **Sign in** link. Any other answer that is not JSON, such as an empty 200, is a failed request for its section and never shows that note. The other sections are not affected.

## REST API

`GET /api/crews` is the same data as the MCP `crews()` tool, available as plain JSON. The endpoint is served by the `ga-radar` container and proxied through Caddy — it is session-gated the same way as `GET /`:

```bash
# No API key (local dev)
curl http://localhost:64057/api/crews | jq

# With API key — requires a valid gs_session cookie (obtain via /dashboard/login)
curl -b gs_session=<token> https://your-host/api/crews | jq
```

Response shape:

```json
{
  "crews": [
    {
      "crew_id": "my-crew",
      "status": "running",
      "acp_backend": "kiro",
      "acp_profile": "default",
      "comp": "spec-ops",
      "composition": "spec-ops",
      "uptime_secs": 1842,
      "last_task_at": "2026-10-29T12:34:56Z",
      "dashboard_url": null,
      "agents": [
        { "task_id": "abc123", "agent": "ghost", "done": false, "elapsed_secs": 47 }
      ],
      "captain": {
        "enabled": true,
        "schedule": "every 600s",
        "current_task_id": "def456"
      }
    }
  ],
  "host_memory_available_gb": 4.1,
  "active_crews": 1,
  "max_active_crews": 6
}
```

`comp` is canonical. During the rollback window, `composition` is an equal-value compatibility alias; clients should read `comp` first and use `composition` as a fallback.

`captain` is `null` when no Captain schedule exists for that crew.

## Mailbox subjects

Expanding a crew row also loads the subject lines of its eight mailboxes: `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral`. Radar groups them by mailbox. An empty mailbox shows `No messages.`. If the crew's mailboxes cannot be read completely, the section shows one `Mailbox subjects unavailable.` state for the whole crew. It never shows a partial list or a false empty state.

- Subjects load only when the row is expanded, not on each five-second fleet poll. Reopening the row fetches a fresh snapshot.
- Running and stopped crews both work. A stopped crew is read from its filesystem and is not started.
- Reading never marks a message as read or changes any mailbox.
- Only subject strings are returned. Message bodies, senders, dates, and counts are never included.
- Each mailbox shows its 50 most recent subjects, newest first. Each subject is cut to 200 characters.

The browser calls `GET /api/crews/{crew_id}/mail-subjects`. Radar forwards the request to the transport's portside-internal `GET /internal/crews/{crew_id}/mail-subjects`, which requires `X-Transport-Token`. Browser access requires the same Portal `gs_session` as the rest of Radar.

```bash
curl -b gs_session=<token> https://your-host/api/crews/my-crew/mail-subjects | jq
```

Response shape:

```json
{
  "mailboxes": {
    "ghost": ["Handoff: TRN-370 radar subjects"],
    "spectre": [],
    "banshee": ["Review requested: mailbox endpoint"],
    "wraith": [],
    "reaper": [],
    "raven": ["Check-in: queue empty"],
    "captain": [],
    "admiral": []
  }
}
```

Radar always answers these failures with `502`. When the transport answered, the body reports its status: `{"error": "transport error", "status_code": 503}` when the mailbox source could not be read, or `404` for an unknown crew. When the transport cannot be reached, the body is `{"error": "transport unreachable"}`. The browser shows the unavailable state for all of them.

## Refresh a crew's auth

Expand a crew row and find its **Credentials** section, then click **Refresh auth**. Radar asks the transport to re-apply the credential currently stored for that crew's backend and profile. [Refresh a crew's auth](auth.md#refresh-a-crews-auth) explains what a refresh does and does not do. In short, it never starts, stops or recreates a crew, and it sends no credential.

The section is shown for running and stopped crews. While a request is in flight the button is disabled and reads `Refreshing…`, so a second click does nothing. After 10 seconds a `Still working…` note appears beside it, because a refresh can take up to a minute. If no answer arrives within 75 seconds, Radar aborts the request and shows the timeout result below. The 75-second limit sits above Radar's 60-second bound on the transport, so it only fires when Radar or the proxy in front of it has stopped answering. The result appears beside the button. It stays visible across the five-second fleet refresh and is cleared when the row is collapsed and reopened. Each crew is refreshed independently.

Radar shows one of these results, followed by the transport's guidance text:

| Result shown | Transport `status` | Meaning and what to do |
|:-------------|:-------------------|:-----------------------|
| `Refreshed.` | `refreshed` | The stored login-flow credential was injected into the running crew. Nothing to do. |
| `Pending until wake.` | `pending_on_wake` | The crew is stopped. It receives the stored credential when it wakes. |
| `Already current.` | `current` | Static credential: the container already holds the stored value. |
| `Recreate required.` | `recreate_required` | The stored static credential or its method differs from the container's, which cannot change in place. Recreate the crew with its workspace preserved, as described in [auth.md](auth.md#refresh-a-crews-auth). |
| `No credential stored.` | `credential_missing` | Nothing is stored for the crew's backend and profile. Run `ghostship auth login <backend>`, then refresh again. |
| `Refresh failed.` | `refresh_failed` | The comparison or injection failed and the crew was left as it was. Check the transport log, then retry. |

When Radar cannot show one of those results, it says why instead:

| Shown | Cause | What to do |
|:------|:------|:-----------|
| `Session expired.` and a **Sign in again** link | Your portal session ended, so the request was redirected to the login page, or answered with HTTP 200 and an HTML page. Nothing was refreshed. | Sign in again, then retry. |
| `Refresh did not complete.` | Radar got no result. The transport was unreachable or answered with an error (HTTP 502, 503 or 504; Radar itself answers 502), Radar refused the request's origin (403), the reply was another unexpected status, or the network failed. | Check that `ga-transport` is running, then retry. A retry is safe: it only re-applies the stored credential. |
| `Refresh did not complete: no answer after 75 seconds.` | No answer came within 75 seconds, so Radar gave up waiting. The refresh may still finish on the transport. This is not a fixed result. | Check the crew (its Credentials result and its agents), then retry. A retry is safe. |
| `Refresh result unknown.` | The reply was not a result Radar recognises. | Retry. If it repeats, check the transport log. |

### Browser API and the same-origin rule

The button calls `POST /api/crews/{crew_id}/auth/refresh` with no body. Radar forwards it to the transport's portside-internal `POST /internal/crews/{crew_id}/auth/refresh` with `X-Transport-Token` and returns the transport's JSON unchanged. Radar holds no backend credential and passes on none of the browser's cookies or headers.

| Radar answers | When |
|:--------------|:-----|
| `200` and the transport's body | The transport returned a result. |
| `403` `{"error": "cross-origin request rejected"}` | The request lacks a same-origin `Origin` header (see below). The transport is not called. |
| `404` `{"error": "crew not found"}` | The crew id is not a valid crew id. The transport is not called. |
| `405` | The method is not `POST`. |
| `502` `{"error": "transport unreachable"}` | Radar could not reach the transport within 60 seconds. |
| `502` `{"error": "transport error", "status_code": <n>}` | The transport answered with a status other than 200, for example 404 for an unknown crew. |

This is the only Radar request that changes anything, and the portal session alone does not protect it. The `gs_session` cookie is `SameSite=Lax`, so a browser still sends it with requests that come from other pages on the same site. Radar therefore requires exactly one `Origin` header whose host and port equal the `Host` header of the request, and answers anything else with `403`. Browsers add `Origin` to every `fetch` POST themselves, so the button needs no token. A request without an `Origin`, such as plain `curl`, is refused. If another reverse proxy sits in front of the portal, it must pass the `Host` header through unchanged, or every refresh is refused.

This endpoint exists for the Radar page. Scripts and other tools should use the transport's operator endpoint, described in [auth.md](auth.md#refresh-a-crews-auth).

### Who can use it

With `GA_API_KEY` set, the action sits behind the same portal session as the rest of Radar. The portal checks `gs_session` first, and a request without a valid session is redirected to `/dashboard/login` and never reaches Radar.

**Tailscale-gated installs have no portal session.** When `GA_API_KEY` is unset, the session check is skipped (see [Auth](#auth)), so anyone who can reach Radar on the tailnet can click the button or send the request. The same-origin rule still stops other web pages from sending it on their behalf. The action is limited: it can only re-apply the credential already stored for that crew's own backend and profile. It cannot supply or choose a credential, and it cannot change a crew's state.

## Auth

Radar is session-gated via `gs_session` cookie. No bearer token needed for `GET /` or `GET /api/crews`. When `GA_API_KEY` is unset, session check is skipped. See [portal.md#auth](portal.md#auth). The one `POST`, [Refresh auth](#refresh-a-crews-auth), also requires a same-origin `Origin` header, with or without a key.
