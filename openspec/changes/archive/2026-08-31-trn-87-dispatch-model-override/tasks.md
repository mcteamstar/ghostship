## 1. Transport-side model validation helper

- [x] 1.1 Add a `_validate_model(model: str | None) -> str | None` helper in `transport/server.py` (or a shared validation module) mirroring KiroCrew's own rule: reject non-`str`, reject length > 500, reject values not matching `^[a-zA-Z0-9][a-zA-Z0-9._-]*$`; return `None` unchanged when input is `None` or empty. Verify with unit tests covering a valid value, `None`, empty string, non-string, overlong string, and a string with invalid characters.

## 2. dispatch() model passthrough

- [x] 2.1 Add an optional `model: str | None = None` parameter to `dispatch()` in `transport/server.py`, validate it via `_validate_model`, and include `"model": model` in the `/api/spawn` request body only when non-empty. Verify with a unit test asserting the request body includes `model` when provided and omits the key entirely when not.
- [x] 2.2 Return a clear validation error (no crew API call) when `model` fails validation. Verify with a unit test asserting `_crew_api_with_recovery` is not called for a malformed `model`.
- [x] 2.3 Update `dispatch()`'s docstring to document the new `model` parameter, and state explicitly that it outranks `KC_MODEL_OVERRIDE` and per-agent config for that one call (not the other way around).

## 3. schedule() model passthrough

- [x] 3.1 Add an optional `model: str | None = None` parameter to `schedule()`, validate it via `_validate_model`, and include `"model": model` in the `/api/crons` request body only when non-empty. `schedule()` builds this body in two separate places — the one-shot `delay` path (`transport/server.py:2227`) and the shared `cron`/`interval` path (`transport/server.py:2265`) — both need the field. Verify with unit tests covering all three job-creation paths (`cron`, `interval`, `delay`).
- [x] 3.2 Update `schedule()`'s docstring to document the new `model` parameter.

## 4. captain(action="order") model passthrough

- [x] 4.1 Add an optional `model: str | None = None` parameter to `captain()`, validate it via `_validate_model`, and include `"model": model` in the `/api/crons` request body only on the create-new-job path (not on resume-existing-job or toggle-enable paths). Verify with unit tests for: new job with model set, new job without model, and resumed job with model set (asserting model is ignored, not an error).
- [x] 4.2 Update `captain()`'s docstring to document the new `model` parameter and that it has no effect on resume.

## 5. Documentation

- [x] 5.1 Update `.claude-plugin/skills/ghostship-command/SKILL.md` to document the new `model` parameter on `dispatch`, `schedule`, and `captain(action="order")`, including that it's create-time-only (no effect via `steer`/`continue`) and that it outranks a crew's `KC_MODEL_OVERRIDE` — an operator relying on `KC_MODEL_OVERRIDE` as an absolute model ceiling should know any dispatch caller can override it per-call.

## 6. Verification

- [x] 6.1 Run the full unit test suite and confirm no regressions.
- [x] 6.2 Manually dispatch a task with an explicit `model` against a live crew and confirm (via `pickup` or crew logs) the session actually served the requested model, distinguishing `model` (requested) from `resolved_model` (served) per `subagent.py`'s existing audit fields. -- **VERIFIED by the Admiral** against a live `trn-87-dispatch-model-override` crew (task `72fa6db9`, `dispatch(model="claude-sonnet-5")`): `~/.kiro/crew/subagents/72fa6db9/state.json` shows `"requested_model": "claude-sonnet-5", "resolved_model": "claude-sonnet-5"` -- both match, confirming the override is forwarded end-to-end and actually served, not just self-reported by the agent.

## 7. Review follow-ups

- [x] 7.1 Persist scheduled-job model pins in the transport registry and forward them on restart re-seeding and transport-owned schedule-monitor ticks; cover the restored request body and registry behavior with unit tests.
- [x] 7.2 Forward a scheduled model pin to `fire_immediately` spawns for both `schedule` and Captain check-ins, with unit coverage for the immediate requests.
