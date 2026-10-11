# Tasks — TRN-220 Internal-API Peer-Cred Compatibility

## Verification (do first — confirms the proposal's premise)

> NOTE: The four verification tasks below require a running crew on the live
> `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` image. That image launch is
> gated by TRN-219 (the 0.9.0 crew-image bump) and requires podman + registry
> access not available from this implementation worktree. They are left
> unchecked for the operator/Reaper to execute once a 0.9.0 crew is live; the
> guardrail code and regression test below do not depend on them.

- [ ] Launch a crew on `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4` (pinned tag or immutable digest). *(deferred — needs live 0.9.0 image / TRN-219)*
- [ ] Issue a cookie-auth REST call through `_crew_api` (e.g. `GET /api/spawn`) and confirm a 2xx response. *(deferred — needs live 0.9.0 crew)*
- [ ] From inside the container, confirm Raven's cookie-path call (`kirocrew spawn list`, or `POST /api/spawn` with `Cookie: mc_token_5476=<value>`) succeeds. *(deferred — needs live 0.9.0 crew)*
- [ ] Confirm an internal-secret call (`X-Internal-Secret`) issued from the transport host is rejected on 0.9.0 (negative check that documents the boundary). *(deferred — needs live 0.9.0 crew)*

## Guardrail code

- [x] Add `_FORBIDDEN_INTERNAL_HEADERS = ("X-Internal-Secret", "X-Session-Key")` near `_crew_api` in `transport/lifecycle.py`.
- [x] Add the TRN-220 comment to `_crew_api` explaining the cookie-path invariant.
- [x] Add the forbidden-header guard in `_crew_api` (reject `X-Internal-Secret` / `X-Session-Key` if ever passed via `headers=`).
- [x] Confirm no existing caller of `_crew_api` passes `headers=` (grep `_crew_api(` across `transport/`); if any does, verify it is compatible with the new merge path. *(grep confirmed zero callers pass `headers=`; the merge path is forward-compatible regardless.)*

## Prompt invariant (already present — assert it stays)

- [x] Confirm `transport/captain.py::_RAVEN_GATEWAY_ORIENTATION` still forbids `X-Internal-Secret` / `X-Session-Key` and documents the `.dashboard_cookie` path. *(verified present and unchanged.)*

## Tests

- [x] Create the `transport/tests/` package if it does not exist. *(DEVIATION: the repo's actual unit-test harness lives in `tests/unit/` and depends on `tests.unit._stubs.install_import_stubs()` to make `transport.lifecycle` importable in the dependency-free checkout; `tests/run.sh` runs `pytest tests/unit`. A test placed under `transport/tests/` would not be discovered and could not use that stub harness. The test was therefore created at `tests/unit/test_trn220_crew_api_headers.py` instead, matching every prior TRN test. No `transport/tests/` package was created.)*
- [x] Add `transport/tests/test_trn220_crew_api_headers.py` asserting `_crew_api` emits `Cookie` + `Origin` only and never the internal-secret headers. *(implemented as `tests/unit/test_trn220_crew_api_headers.py` — 4 tests: cookie-path-only, exactly Cookie+Origin, forbidden-header rejection, benign-header merge.)*
- [x] Run the test suite and confirm the new test passes. *(4 passed; `tests/unit/test_lifecycle.py` + `test_recovery.py` = 122 passed, no regression.)*

## Documentation

- [x] Add a one-line note to the upgrade changelog/notes: "TRN-220 — internal-API peer-cred validation (PR #2424) does not affect ghostship; transport uses the cookie path. Guardrail test added." *(added under a new `## KiroCrew 0.8.0 → 0.9.0 upgrade` section at the top of `CHANGELOG.md`.)*
- [ ] Record the verification result (2xx on cookie path against 0.9.0-insider.4) in the ticket. *(deferred — depends on the live-image verification tasks above.)*

## Close-out

- [ ] Mark TRN-220 as verified / resolved in Plane with the verification evidence attached. *(deferred — operator/close-out step; requires Plane access and the verification evidence from the deferred tasks above.)*
