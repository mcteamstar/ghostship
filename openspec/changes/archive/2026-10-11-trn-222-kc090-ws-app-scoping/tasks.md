# Tasks: TRN-222 — WS Scoping & Redaction Verification

Verification-only change. No production code is modified; each task confirms an
invariant against the source and/or the running `0.9.0-insider.4` gateway.

## Source audit (static)

- [x] Confirm `CaddyPortal.register_crew` in `transport/caddy.py` still builds the WS route by matching `{"header": {"Connection": ["Upgrade"]}}` and handling it with `crew_proxy_handler`.
- [x] Confirm `crew_proxy_handler` sets only `X-Transport-Token` on the upstream request and sets no `X-App-Token` (or any app-token header).
- [x] Confirm the TRN-189 WS-route comment still accurately describes cookie-inherited auth (WS inherits the `gs_session` validated on the SPA's HTTP load).
- [x] Confirm `DashboardGate.handle_auth` in `transport/dashboard.py` validates only the `gs_session` cookie and never reads a WS payload body.
- [x] Grep `transport/` for `tool_title` and `assistant_content` reads on the WS path; confirm none exist.

## Runtime verification (against 0.9.0-insider.4)

- [~] Build/start a crew with `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`. — **BLOCKED:** no container runtime (podman/docker/nerdctl/containerd) in the agent environment; cannot build or start a gateway image here.
- [~] Log into the dashboard and open the browser dev-tools WS inspector; confirm the WS upgrade request carries the `gs_session` cookie and no `X-App-Token` header. — **BLOCKED:** depends on a running gateway (above).
- [~] Confirm the dashboard WS stream still delivers crew session lifecycle events (turn started, turn ended, new message) without per-app filtering. — **BLOCKED:** depends on a running gateway (above).
- [~] Open a running session and confirm full assistant text and tool-call content render in the portal (sourced from REST `GET /api/sessions/{id}/messages`), despite WS broadcast redaction. — **BLOCKED:** depends on a running gateway (above).
- [~] Confirm no portal console errors referencing missing `assistant_content` / `tool_title` from WS payloads. — **BLOCKED:** depends on a running gateway (above).

> Runtime tasks are `[~]` BLOCKED, not failed: they require a live
> `0.9.0-insider.4` gateway, which cannot be built or started in this
> environment (no container runtime). They are deferred to manual/CI
> verification. The static source audit is complete and all-pass.

## Record / sign-off

- [x] Record the verification outcome (pass/fail per check) in the change notes.
- [~] If all checks pass, mark TRN-222 as verified-no-change for the 0.9.0 upgrade. — **PARTIAL:** static audit all-pass; runtime checks still PENDING (blocked above), so the `verified-no-change` sign-off cannot be fully claimed from this run. Static evidence found no failure.
- [x] If any check fails, re-open with a concrete code task referencing the failing file/function and escalate the priority verdict above "low impact". — Resolved: **no check failed.** All static checks pass and no runtime failure was observed; no re-open and no priority escalation. Priority verdict stays "BEHAVIOUR CHANGE / LOW IMPACT — verification only".
- [x] Add the D3 future-break guard note to the WS-proxy code review checklist so any future app-token WS change re-opens this baseline.
