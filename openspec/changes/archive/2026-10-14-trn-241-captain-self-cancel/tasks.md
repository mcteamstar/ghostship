# Tasks

## 1. Inject KIROCREW_CREW_ID

- [x] 1.1 In `transport/server.py`, locate the `container_env` dict construction in the `launch` function (~line 2751, next to `"KIROCREW_CORS_ORIGINS": _cors_origins`). Add `"KIROCREW_CREW_ID": crew_id` to the same dict. Verify: search confirms `KIROCREW_CREW_ID` appears in the container env; `pytest tests/unit/ -q` green.

## 2. Test

- [x] 2.1 In the existing server/launch unit tests (or a new `test_trn241_crew_id_env.py`), add an assertion that the `container_env` passed to `podman.container_create` contains `KIROCREW_CREW_ID` equal to the launched crew_id. Verify: test passes; `pytest tests/unit/ -q` green.

## 3. Spec delta

- [x] 3.1 Write `openspec/changes/trn-241-captain-self-cancel/specs/crew-lifecycle/spec.md`. Add requirement: the crew container environment MUST include `KIROCREW_CREW_ID` set to the crew's identifier so that crew-internal scripts (including the Raven self-cancel mechanism) can address the transport without parsing `KIROCREW_CORS_ORIGINS`.

## Workflow follow-up

- Archive the change after review.
