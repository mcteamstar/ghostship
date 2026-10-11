# Tasks — TRN-220 Internal-API Peer-Cred Compatibility

## Verification (do first — confirms the proposal's premise)

- [ ] Launch a crew on `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (pinned tag or immutable digest).
- [ ] Issue a cookie-auth REST call through `_crew_api` (e.g. `GET /api/spawn`) and confirm a 2xx response.
- [ ] From inside the container, confirm Raven's cookie-path call (`kirocrew spawn list`, or `POST /api/spawn` with `Cookie: mc_token_5476=<value>`) succeeds.
- [ ] Confirm an internal-secret call (`X-Internal-Secret`) issued from the transport host is rejected on 0.9.0 (negative check that documents the boundary).

## Guardrail code

- [ ] Add `_FORBIDDEN_INTERNAL_HEADERS = ("X-Internal-Secret", "X-Session-Key")` near `_crew_api` in `transport/lifecycle.py`.
- [ ] Add the TRN-220 comment to `_crew_api` explaining the cookie-path invariant.
- [ ] Add the forbidden-header guard in `_crew_api` (reject `X-Internal-Secret` / `X-Session-Key` if ever passed via `headers=`).
- [ ] Confirm no existing caller of `_crew_api` passes `headers=` (grep `_crew_api(` across `transport/`); if any does, verify it is compatible with the new merge path.

## Prompt invariant (already present — assert it stays)

- [ ] Confirm `transport/captain.py::_RAVEN_GATEWAY_ORIENTATION` still forbids `X-Internal-Secret` / `X-Session-Key` and documents the `.dashboard_cookie` path.

## Tests

- [ ] Create the `transport/tests/` package if it does not exist.
- [ ] Add `transport/tests/test_trn220_crew_api_headers.py` asserting `_crew_api` emits `Cookie` + `Origin` only and never the internal-secret headers.
- [ ] Run the test suite and confirm the new test passes.

## Documentation

- [ ] Add a one-line note to the upgrade changelog/notes: "TRN-220 — internal-API peer-cred validation (PR #2424) does not affect ghostship; transport uses the cookie path. Guardrail test added."
- [ ] Record the verification result (2xx on cookie path against 0.9.0-insider.4) in the ticket.

## Close-out

- [ ] Mark TRN-220 as verified / resolved in Plane with the verification evidence attached.
