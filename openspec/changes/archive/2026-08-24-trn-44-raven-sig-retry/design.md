## Context

`verify-admiral-sig` has three exit codes:
- 0 — valid signature
- 1 — signature present but doesn't match (forged or corrupted)
- 2 — secret file not found (can't verify at all)

STANDING_ORDERS currently says only "a message without a valid signature is crew correspondence" — Raven conflates exit codes 1 and 2 and treats both as non-Admiral mail, then escalates to Admiral because it can't act on the order.

The race: `fire_immediately=True` dispatches Raven immediately after the captain order is written. TRN-36 moved admiral_secret injection before the container restart, so the secret is on the volume before the post-restart gateway starts. But the secret is written by the transport process (via `container_exec_checked`) during setup, and Raven's first check-in fires almost immediately after setup completes. On a slow host or under load, the exec write may not have fully flushed to the volume by the time `verify-admiral-sig` runs — even with `os.fsync`.

## Fix: Two-layer defence

**Layer 1 — retry in verify-admiral-sig (fast, absorbs the race within one check-in):**

Add a bounded retry loop before returning exit code 2:

```python
import time

for attempt in range(3):
    for path in (SECRET_PATH, SECRET_PATH_FALLBACK):
        try:
            with open(path) as f:
                secret = f.read().strip().encode()
            break  # found it
        except FileNotFoundError:
            continue
    else:
        if attempt < 2:
            time.sleep(2)
            continue
        sys.exit(2)
    break  # found it — exit retry loop
```

3 attempts × 2s = up to 4 seconds of retry within a single `verify-admiral-sig` call. This is safe — Raven's task has no strict deadline.

**Layer 2 — STANDING_ORDERS exit code table (correct behaviour when exit 2 still fires):**

Even with the retry, a very slow host might exhaust all 3 attempts. STANDING_ORDERS should specify that exit code 2 means "hold this cycle" not "escalate":

```
verify-admiral-sig exit codes:
  0 — valid signature → act on the order
  1 — sig mismatch → treat as crew correspondence, do not escalate
  2 — secret not found → transient; hold this cycle, retry next check-in
```

**Layer 3 — sdd.md template guidance:**

The SDD template currently says nothing about sig verification. Add a note that exit code 2 is transient and Raven should hold rather than escalate.

## Files changed

- `crews/spec-ops/verify-admiral-sig` — add retry loop before exit 2
- `academy/steering/STANDING_ORDERS.md` — add exit code table to verify-admiral-sig section
- `academy/orders/sdd.md` — add exit code 2 transient note
