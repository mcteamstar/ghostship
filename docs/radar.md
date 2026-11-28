# Radar — Fleet Dashboard

Radar is the ghostship fleet observability dashboard. Opening `GET /` in a browser shows all crews, their status, active tasks, Captain state, and schedule — no MCP agent session required.

## Accessing Radar

Navigate to the transport URL in a browser:

```
http://localhost:64057/          # local dev (no API key)
https://your-portal-hostname/    # production (API key required)
```

When `GA_API_KEY` is set, you will be redirected to `/dashboard/login` first. Log in once; the `gs_session` cookie covers all subsequent dashboard and Radar requests in the same browser session.

## Fleet and crew views

The sidebar opens Fleet. The Ghost Academy header shows running and stopped totals, available capacity and memory when reported, and the last successful refresh. `Capacity` and `Free memory` are omitted if the fleet does not report them. Radar follows the system colour preference.

Search stays visible whenever the fleet is shown. With zero matches Radar shows `No crews match filter.` and offers to clear filters. Below 640 px, List uses stacked rows.

Choose **List** or **Cards** to change how the same crews are displayed. Search by crew ID or comp, combine search with a status filter, and choose newest created or either Last Task order. In List, use the Last task column heading to cycle through the sort orders. Cards and narrow lists show a Sort dropdown beside search. **Needs attention** includes an unhealthy gateway on a running crew or a stale enabled Captain. A stopped crew alone does not need attention.

Select a crew to open its inspector. At wide widths it appears beside the fleet. At narrow widths **Back to fleet** returns to the previous list position. The selected crew, filters and presentation survive polling. A link ending in `#crew=<id>` opens that crew directly.

**Overview** shows crew metadata, active and finished agent tasks, Captain details and **Refresh auth**. Tasks appear under `Running · N` and `Finished · N`. A missing agent name reads `unknown agent`, and an empty running group reads `No active tasks.` The inspector header provides available dashboard and copy actions. A failed task read shows `Active tasks unavailable.` and a pending read shows `Loading tasks…`.

**Mailbox** shows retained delivery metadata as a newest-first timeline. Choose **Sender** or **Recipient** to group the same deliveries. Recipient is the receiving mailbox. Subjects wrap and missing values are labeled. Empty mailboxes show `No messages.`, and an unreadable history shows `Mailbox history unavailable.` While waiting, Radar says `Loading mailbox history…`. Expired sessions show `Session expired, sign in again`; other non-JSON responses show a request failure. A successful snapshot displays a note when it reaches the per-mailbox limit.

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

The existing `GET /api/crews/{crew_id}/mail-subjects` endpoint remains available for compatibility. The inspector uses `GET /api/crews/{crew_id}/mail-history` under the same portal session. It returns up to 50 retained deliveries per mailbox, each with nullable `subject`, `sender` and `timestamp`, plus a `capped` flag. The mailbox key identifies the recipient. Both endpoints exclude mail bodies and attachments and can read stopped crews without waking them.

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
