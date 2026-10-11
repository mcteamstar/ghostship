# Change Notes: TRN-222 — WS Scoping & Redaction Verification

**Verified by:** Ghost  
**Date:** 2026-10-11  
**Against:** ghostship source (worktree `trn-222-kc090-ws-app-scoping`)

---

## Source audit results (static) — ALL PASS

### SA-1: WS route match and handler (caddy.py)
**PASS.** `CaddyPortal.register_crew` (lines 202–205) builds:

```python
ws_route = {
    "match": [{"header": {"Connection": ["Upgrade"]}}],
    "handle": [crew_proxy_handler],
}
```

Exactly as specified.

### SA-2: No `X-App-Token` in crew_proxy_handler (caddy.py)
**PASS.** `crew_proxy_handler` (lines 147–156) sets only:

```python
"headers": {"request": {"set": {
    "X-Transport-Token": ["{file./run/secrets/ga-transport-secret}"],
}}},
```

Grep of all `transport/` for `X-App-Token`, `app.token`, `app_token` — **zero matches**.

### SA-3: TRN-189 WS-route comment accuracy (caddy.py)
**PASS.** Comment at lines 192–201 accurately describes the auth model:

> No auth regression: reaching this port at all required the gs_session that
> forward_auth validated on the SPA's initial HTTP load, and the WS inherits
> that authenticated browser context.

### SA-4: DashboardGate.handle_auth reads only gs_session cookie (dashboard.py)
**PASS.** `handle_auth` (lines 185–244) reads only:

```python
token = request.cookies.get("gs_session", "")
```

No WS payload body is accessed. No `X-App-Token` read. Returns 200/401 only.

### SA-5: No tool_title / assistant_content reads on WS path (transport/)
**PASS.** Grep of entire `transport/` directory for `tool_title` and
`assistant_content` — **zero matches**. The transport does not decode WS frame
bodies; it reverse-proxies them.

---

## Runtime verification (against 0.9.0-insider.4) — PENDING

Runtime checks require a live `0.9.0-insider.4` gateway environment. No
container runtime (podman/docker) is available in the agent environment where
static audit ran. These tasks remain open for manual or CI verification:

- [ ] WS upgrade request carries `gs_session` cookie and no `X-App-Token` (browser dev-tools)
- [ ] Dashboard WS stream delivers full crew session lifecycle events (no per-app filtering)
- [ ] Full assistant text and tool-call content render in portal (sourced from REST)
- [ ] No portal console errors for missing `assistant_content` / `tool_title` from WS

Static evidence strongly supports all four runtime checks passing: the source
confirms cookie-only auth on the WS path and no WS content reads in the portal
transport code. Runtime checks are confirmatory, not exploratory.

---

## D3 future-break guard

Per design section D3, any PR that introduces app-token-authenticated WS
connections to ghostship MUST re-open this baseline and explicitly decide
whether the app token should see cross-app events. This is now recorded in the
change notes and should be added to the WS-proxy code review checklist.

**Code review checklist item (add to PR template or Caddy/WS review notes):**
> If this change adds `X-App-Token` to any WebSocket proxy path, re-open
> TRN-222 and verify that per-app event scoping in KiroCrew 0.9.0+ does not
> hide events the portal depends on.
