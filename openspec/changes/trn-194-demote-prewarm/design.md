# Design: Demote prewarm from MCP tool to internal function

## Context

The prewarm machinery lives across three files:
- `transport/lifecycle.py` — `_prewarm_crew`, `prewarm` (public wrapper), `_issue_warmup`, `_effective_prewarm_ttl`, warm-marker state
- `transport/server.py` — `prewarm` MCP tool, `_handle_crew_prewarm_post` REST handler, route table entries
- `transport/auth.py` — two prewarm-specific short-circuits in the auth middleware

## D1 — Remove the MCP tool

`transport/server.py`: delete the `def prewarm(...)` function decorated with `@mcp.tool()`. Also delete the two `import` aliases (`prewarm as prewarm_impl`) from the lifecycle imports at the top of the file (~lines 667–668 and 754–755).

## D2 — Remove the REST route and handler

`transport/server.py`: delete `_handle_crew_prewarm_post` and both route table entries:
```python
(\"POST\", \"/crews/*/prewarm\"): _handle_crew_prewarm_post,
```
Both entries appear (one for unauthenticated, one for authenticated route tables) at lines ~4250 and ~4288.

## D3 — Remove auth special-casing

`transport/auth.py`: remove the two prewarm-specific branches at ~lines 508–518 and ~626–637. After removal, `POST /crews/{id}/prewarm` falls through to the generic unrecognised-route handler and returns 404.

## D4 — Remove the public wrapper in lifecycle.py

`transport/lifecycle.py`: delete the `def prewarm(crew_id: str | None) -> dict` function (~line 922). The only callers were the MCP tool and REST handler, both now gone.

## D5 — Implicit trigger from `supply`

`transport/server.py`, inside `def supply(...)`, after the `_security.audit_auth_event(...)` call and before the `return` statement:

```python
if GA_PREWARM_ENABLED:
    _bg_prewarm(crew, crew_id)
```

where `_bg_prewarm` is a small helper (can be defined once, reused from `schedule`):

```python
def _bg_prewarm(crew: dict, crew_id: str) -> None:
    \"\"\"Fire-and-forget background prewarm. Non-fatal.\"\"\"
    def _run() -> None:
        try:
            _prewarm_crew(crew, crew_id)
        except Exception as exc:
            logger.warning(\"Background prewarm for %s failed (non-fatal): %s\", crew_id, exc)
    threading.Thread(target=_run, daemon=True).start()
```

No `GA_PREWARM_ENABLED` guard needed around `_bg_prewarm` — `_prewarm_crew` already returns early when disabled. The guard is optional but makes the fast path clearer.

## D6 — Implicit trigger from `schedule`

`transport/server.py`, inside `def schedule(...)`, after the registry write succeeds for all three job types (cron, interval, and delay), add:

```python
_bg_prewarm(crew, crew_id)
```

The `crew` variable is already resolved in each path by the time we reach the registry write. All three job-creation branches (delay, interval, cron) must include the trigger.

## D7 — Test changes

`tests/unit/test_prewarm.py`:
- Delete `TestPrewarmHandler` (tests for `_handle_crew_prewarm_post`)
- Delete `TestPrewarmMiddleware` (tests for auth middleware dispatch)
- Retain `TestPrewarmCore` and `TestPrewarmTTL`

New test class `TestPrewarmImplicitTriggers` (same file or a new `test_prewarm_implicit.py`):
- `test_supply_fires_background_prewarm` — mock `_prewarm_crew`, call `supply(...)`, assert the mock was called
- `test_supply_prewarm_exception_is_nonfatal` — make `_prewarm_crew` raise, assert `supply` still returns success
- `test_schedule_fires_background_prewarm` — mock `_prewarm_crew`, call `schedule(action="create", ...)`, assert called
- `test_schedule_prewarm_exception_is_nonfatal` — same raise pattern

Use `threading.Event` or `unittest.mock.patch` with side-effect to synchronise the background thread before asserting.

New test class `TestConfigPrewarmDefaults` in `tests/unit/test_config_from_env.py`:
- `test_ga_prewarm_enabled_default_off` — clear `GA_PREWARM_ENABLED` from env, assert `Config.from_env().ga_prewarm_enabled == False`
- `test_ga_prewarm_enabled_on_when_explicitly_set` — set `GA_PREWARM_ENABLED=1`, assert `True`
- `test_ga_prewarm_ttl_secs_default` — clear `GA_PREWARM_TTL_SECS`, assert `Config.from_env().ga_prewarm_ttl_secs == 300`

Additional tests in `test_prewarm.py`:
- `test_disabled_is_the_module_default` — import `lifecycle` with `GA_PREWARM_ENABLED` unset, assert `lifecycle.GA_PREWARM_ENABLED is False` (the demote invariant as a structural assertion)
- `test_generic_runtime_error_returns_start_failed` — patch `_ensure_crew_running` to raise `RuntimeError("container image not found")`, assert result is `{"crew_id": ..., "status": "blocked:start-failed"}`
- `test_ttl_zero_disables_idempotency_check` — patch `GA_PREWARM_TTL_SECS=0` with a fresh warm marker in `_warm_markers`, assert result is NOT `already_warm` and `_crew_api_with_recovery` was called

Side-effect patches to remove from other test files:
- `tests/unit/test_trn170_claude_subscription_oauth.py` ~line 360: `GA_PREWARM_ENABLED=False` patch becomes unnecessary
- `tests/unit/test_trn172_codex_backend.py` ~line 164: same

## D8 — Docs

`CHANGELOG.md`: find the TRN-131 entry and replace the "no-op canary dispatch" description with: `_issue_warmup sends GET /api/ready to warm the ACP session`.

`docs/configuration.md`: remove the `prewarm` tool section, the `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` rows from the env vars table, and any mention of `POST /crews/{id}/prewarm`.

`scripts/install.sh`: remove the `GA_PREWARM_ENABLED` and `GA_PREWARM_TTL_SECS` lines (~line 752). These were baking in `GA_PREWARM_TTL_SECS=0`, which contradicts the documented default of `300` and disables the idempotency check for any deployment with prewarm enabled — a pre-existing correctness bug that goes away with removal.

`config/ghostship.conf.example`: remove the prewarm section (lines ~93–106).

## D9 — Archive stale specs

`openspec/specs/acp-prewarm/spec.md`: delete the file and its directory. The live spec described the MCP tool and REST endpoint surface — both removed.

`openspec/specs/crew-lifecycle/spec.md`: remove the warm-marker eviction requirement block (lines ~719–736). This requirement describes `_warm_markers`, `_warm_markers_lock`, and `_WARM_MARKER_TTL_SECS` — all removed with the internal machinery.

## Breaking change note

The `prewarm` MCP tool and `POST /crews/{id}/prewarm` are removed. Include in CHANGELOG under "Breaking changes" for the next version.
