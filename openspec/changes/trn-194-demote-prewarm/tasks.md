# Tasks: Demote prewarm from MCP tool to internal function

## 1. Remove public surface from transport/server.py

- [ ] 1.1 Delete the `def prewarm(...)` MCP tool function
- [ ] 1.2 Delete the two `prewarm as prewarm_impl` import aliases from the lifecycle imports (~lines 667–668, 754–755)
- [ ] 1.3 Delete the `_handle_crew_prewarm_post` REST handler function
- [ ] 1.4 Delete both route table entries `("POST", "/crews/*/prewarm"): _handle_crew_prewarm_post` (~lines 4250, 4288)

## 2. Remove auth special-casing from transport/auth.py

- [ ] 2.1 Delete the prewarm short-circuit branch at ~lines 508–518 (unauthenticated path)
- [ ] 2.2 Delete the prewarm short-circuit branch at ~lines 626–637 (authenticated path)

## 3. Remove public wrapper from transport/lifecycle.py

- [ ] 3.1 Delete `def prewarm(crew_id: str | None) -> dict` (~line 922)

## 4. Add implicit prewarm triggers to transport/server.py

- [ ] 4.1 Add the `_bg_prewarm(crew, crew_id)` helper (fire-and-forget daemon thread, exceptions caught and logged at WARNING)
- [ ] 4.2 Call `_bg_prewarm(crew, crew_id)` from `supply` after the presign audit event, before the return
- [ ] 4.3 Call `_bg_prewarm(crew, crew_id)` from the `schedule` delay-job creation path after the registry write
- [ ] 4.4 Call `_bg_prewarm(crew, crew_id)` from the `schedule` interval/cron creation path after the registry write

## 5. Update tests in tests/unit/test_prewarm.py

- [ ] 5.1 Delete `TestPrewarmHandler` class
- [ ] 5.2 Delete `TestPrewarmMiddleware` class
- [ ] 5.3 Verify `TestPrewarmCore` and `TestPrewarmTTL` are untouched and still pass
- [ ] 5.4 Add `test_supply_fires_background_prewarm` to a new `TestPrewarmImplicitTriggers` class
- [ ] 5.5 Add `test_supply_prewarm_exception_is_nonfatal`
- [ ] 5.6 Add `test_schedule_fires_background_prewarm`
- [ ] 5.7 Add `test_schedule_prewarm_exception_is_nonfatal`

## 6. Add missing tests identified by review

- [ ] 6.1 Add `TestConfigPrewarmDefaults` to `tests/unit/test_config_from_env.py`: assert `ga_prewarm_enabled == False` when `GA_PREWARM_ENABLED` is unset (the demote invariant), and `True` when set to `1`
- [ ] 6.2 Add `test_ga_prewarm_ttl_secs_default` asserting `ga_prewarm_ttl_secs == 300` when `GA_PREWARM_TTL_SECS` is unset
- [ ] 6.3 Add `test_disabled_is_the_module_default` to `test_prewarm.py`: assert `lifecycle.GA_PREWARM_ENABLED` is `False` when the module is loaded without the env var set
- [ ] 6.4 Add `test_generic_runtime_error_returns_start_failed` to `test_prewarm.py`: verify that a `RuntimeError` whose message matches neither memory nor active-crew returns `blocked:start-failed`
- [ ] 6.5 Add `test_ttl_zero_disables_idempotency_check` to `test_prewarm.py`: verify that with `GA_PREWARM_TTL_SECS=0` a fresh warm marker does not produce `already_warm`
- [ ] 6.6 Remove `GA_PREWARM_ENABLED=False` side-effect patches from `tests/unit/test_trn170_claude_subscription_oauth.py` (~line 360) and `tests/unit/test_trn172_codex_backend.py` (~line 164) — these patches become unnecessary once prewarm is never auto-triggered

## 7. Documentation cleanup

- [ ] 7.1 Fix CHANGELOG.md TRN-131 entry: replace "no-op canary dispatch" with `GET /api/ready`
- [ ] 7.2 Add breaking change entry for the removed `prewarm` tool and REST route to CHANGELOG.md
- [ ] 7.3 Remove the `prewarm` tool section from `docs/configuration.md` (the `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` rows from the env vars table, and any mention of `POST /crews/{id}/prewarm`)
- [ ] 7.4 Remove the `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` lines from `scripts/install.sh` (~line 752)
- [ ] 7.5 Remove the prewarm section from `config/ghostship.conf.example` (lines ~93–106)

## 8. Archive stale OpenSpec specs

- [ ] 8.1 Delete `openspec/specs/acp-prewarm/spec.md` (and its directory if empty after deletion)
- [ ] 8.2 Remove the warm-marker eviction requirement block from `openspec/specs/crew-lifecycle/spec.md`

## 9. Verification

- [ ] 9.1 Run `tests/run.sh unit` and confirm all unit tests pass
