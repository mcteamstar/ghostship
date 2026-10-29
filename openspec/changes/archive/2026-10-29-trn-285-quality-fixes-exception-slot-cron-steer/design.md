# Design

## Context

Four small targeted fixes. M-1 and M-4 are in exception handling; M-2 is a guard
on an undocumented input value; M-3 fixes a first-fire time calculation. All are
self-contained one-to-five-line changes.

## Goals / Non-Goals

**Goals:** Fix all four correctness issues with minimal code change and add regression
tests for each.

**Non-Goals:** Broader refactoring of the affected modules.

## Decisions

### D1: M-1 — Extend scrypt except clause (`security.py`)

```python
# Before
except (ValueError, TypeError):
    return False

# After
except (ValueError, TypeError, OSError, OverflowError):
    return False
```

One line change. `OSError` covers `maxmem` exceeded on Linux; `OverflowError` covers
extreme `n`/`r`/`p` values that overflow C integer bounds on some platforms. Both are
documented in the Python `hashlib.scrypt` spec as possible raises.

### D2: M-2 — slot=True guard (`lifecycle.py` `_resolve_dispatch_slot`)

```python
# Add at the top of _resolve_dispatch_slot, before existing logic:
if slot is True:
    logger.warning(
        "_resolve_dispatch_slot: slot=True is not a valid value; "
        "treating as slot=None. Pass False for explicit headless or "
        "None for the default member-slot behaviour."
    )
    slot = None
```

Using a warning (not ValueError) to avoid breaking any caller that accidentally
passes `True` — consistent with the transport's general policy of graceful
degradation on invalid-but-recoverable inputs.

### D3: M-3 — Cron first-fire evaluation (`captain_engine.py`)

The existing `advance_next_fire_at` helper in `registry.py` already evaluates cron
expressions (using `croniter` or equivalent). Re-use it for the first-fire
calculation:

```python
# Before (in _captain_do_order, schedule_entry construction):
"next_fire_at": now + 60,

# After:
if effective_cron:
    # evaluate first cron tick after now
    import croniter as _croniter
    first_fire = _croniter.croniter(effective_cron, now).get_next(float)
else:
    first_fire = now + 60  # interval: 60s initial delay unchanged
"next_fire_at": first_fire,
```

Check whether `croniter` is already imported in `captain_engine.py` or `registry.py`
and reuse the existing import path.

### D4: M-4 — httpx status-code classification (`captain_engine.py`)

```python
# Before (in _steer_captain_checkin):
except Exception as exc:
    err_str = str(exc)
    if "400 Bad Request" in err_str and "/continue" in err_str:
        ...

# After:
except httpx.HTTPStatusError as exc:
    if exc.response.status_code == 400 and exc.request.url.path.endswith("/continue"):
        ...
except Exception as exc:
    ...  # other errors fall through to existing handling
```

`httpx` is already imported in `captain_engine.py`. This mirrors the existing pattern
in `_crew_api_with_recovery` at line 830.

## Risks / Trade-offs

- D3 depends on `croniter` being available. If it is not already a dependency, use
  `registry.advance_next_fire_at` as the single evaluation path rather than calling
  `croniter` directly — read the existing implementation during the apply phase.
- D2 chooses warning over ValueError — acceptable because the transport's API layer
  already validates `slot` at the tool boundary and this is a defence-in-depth guard.
