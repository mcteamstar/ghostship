# TRN-186 Angle C: External Spawn + Member Slot Routing

**Date:** 2026-10-02
**Investigator:** Wraith
**Source files examined:**
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew/kiro_crew/dashboard/handlers/messaging.py`
- `/home/kirocrew/workplace/kirocrew-workspace/kirocrew/kiro_crew/dashboard/handlers/_shared.py`

---

## Scenario Under Investigation

An external caller sends:
```
POST /api/spawn
X-Internal-Secret: <valid>
X-Session-Token: (absent)
Body: { "task": "...", "parent_session": "dashboard:member-raven" }
```

Does this route into the member DM slot, or fail? And separately: does X-Internal-Secret alone ever pass attestation through `internal_memory_scope` in `_shared.py`, regardless of `parent_session`?

---

## Findings

### 1. What `X-Internal-Secret` alone does for `internal_auth`

The middleware sets `request["internal_auth"] = True` on any request bearing a valid `X-Internal-Secret`. There is no `X-Session-Token` involved — that is a different header. The header that matters for session identity in the spawn path is `X-Session-Key`.

When `X-Internal-Secret` is present (and valid), `request.get("internal_auth") is True` — this is the "internal caller" class. It bypasses the owner-dashboard check at the top of `api_spawn`:

```python
# messaging.py lines ~477-484
if request.get("internal_auth") is not True and request.get("app") == "":
    owner_denied = await require_owner_dashboard_request(request, "spawn.create")
    if owner_denied is not None:
        return owner_denied
```

So **yes — X-Internal-Secret alone bypasses the owner-dashboard gate**. The caller proceeds into `api_spawn`.

---

### 2. `internal_memory_scope` in `_shared.py` — attestation path

`internal_memory_scope` is defined as:

```python
async def internal_memory_scope(
    request: web.Request, operation: str, *, claimed_session: str | None = None
) -> tuple[str | None, web.Response | None]:
    if request.get("internal_auth") is not True:
        return None, None  # non-internal callers pass straight through
    scope = await member_request_scope(request)
    if scope.verified and (claimed_session is None or claimed_session == scope.session):
        return scope.store or None, None
    # else: audit + 409
    return None, web.json_response(...)
```

The key sub-call is `member_request_scope(request)`, which:
1. Checks `internal_auth is True` (already confirmed)
2. Reads `request.headers.get("X-Session-Key", "")`
3. Calls `session_key_is_attested(request, session)` — this validates that the session key matches the AF/UNIX peer's credentials

**Critical branch — no `X-Session-Key` header:**

When no `X-Session-Key` is present, `session` is `""`. `_resolve()` hits:

```python
if not session:
    return MemberScope(None, True, None)
```

So `scope = MemberScope(session=None, verified=True, store=None)`.

Back in `internal_memory_scope`:
```python
if scope.verified and (claimed_session is None or claimed_session == scope.session):
    return scope.store or None, None
```

`scope.verified` is `True`. The `claimed_session` check:
- `claimed_session is None` → only when `host_cli` path passes `None`
- For the normal spawn call, `claimed_session = parent_session` = `"dashboard:member-raven"`
- `scope.session` is `None`
- So: `claimed_session == scope.session` → `"dashboard:member-raven" == None` → **False**

Since the claimed_session doesn't match `scope.session` (which is `None`), the check **fails** and the function returns a 409 refusal with `member_identity_unavailable`.

**Exception — the `host_cli` path:**

There is a special case in `api_spawn` before `internal_memory_scope` is called:

```python
host_cli = await _is_host_cli_spawn(request, parent_session)
_, refusal = await internal_memory_scope(
    request, "spawn.create", claimed_session=None if host_cli else parent_session
)
```

`_is_host_cli_spawn` returns `True` only when ALL of:
- `request.get("internal_auth") is True` ✓ (our caller has this)
- `not parent_session` — **FAILS** because `parent_session = "dashboard:member-raven"` is non-empty
- `not request.headers.get("X-Session-Key", "")` ✓
- `not request.headers.get("X-Internal-Caller", "")` ✓
- `local_owner_bootstrap_allowed(request)` — checks process ancestry

Because `parent_session` is `"dashboard:member-raven"` (non-empty), `_is_host_cli_spawn` returns `False`. So `claimed_session` is passed as `parent_session = "dashboard:member-raven"`.

Then `internal_memory_scope` is called with `claimed_session="dashboard:member-raven"`, which (as shown above) fails the match against `scope.session=None` and returns a 409.

---

### 3. Route into member DM slot — does it happen?

**No.** The request fails with HTTP 409 `member_identity_unavailable` at the `internal_memory_scope` check, before it ever reaches the member-routing logic (`member_request_scope` / `derive_execution` / `admitted_execution`).

The sequence for the attack scenario is:

```
POST /api/spawn
  X-Internal-Secret: valid  →  internal_auth = True
  no X-Session-Key
  body.parent_session = "dashboard:member-raven"

1. Owner-dashboard gate SKIPPED (internal_auth = True)
2. _is_host_cli_spawn() → False  (parent_session is non-empty)
3. internal_memory_scope(claimed_session="dashboard:member-raven")
   → member_request_scope()
      → session key is "" (no X-Session-Key header)
      → MemberScope(session=None, verified=True, store=None)
   → claimed_session "dashboard:member-raven" ≠ scope.session None
   → returns 409 {"error": "The execution identity is unavailable...",
                  "code": "member_identity_unavailable"}
4. api_spawn returns 409 — SPAWN DOES NOT PROCEED
```

The request never reaches the `member_request_scope` / `derive_execution` block that would route into the crew member's store.

---

### 4. Is there ANY path where X-Internal-Secret alone passes attestation regardless of parent_session?

**Yes — one path:** if the caller omits `parent_session` entirely (empty string).

If `body.get("parent_session", "")` is `""`:
- `_is_host_cli_spawn()` → still `False` unless `local_owner_bootstrap_allowed()` passes (which requires specific process ancestry — effectively the CLI)
- `internal_memory_scope(claimed_session="")` is called
  - `scope.session = None`, `claimed_session = ""`
  - `"" == None` → still False

So even with empty `parent_session`, attestation still fails unless the host CLI process ancestry check passes.

**The only route that actually passes with X-Internal-Secret + no X-Session-Key + no parent_session:**

If `local_owner_bootstrap_allowed(request)` returns `True` (sandboxed agent shells cannot pass this), then `host_cli = True`, and `internal_memory_scope` is called with `claimed_session=None`. With `claimed_session is None`, the check becomes `scope.verified and True` → passes. This returns `scope.store = None`, meaning the Global store.

**So: X-Internal-Secret alone CANNOT route into a member's DM slot under any combination. The strongest it can do is spawn into the Global store via the CLI host-operator path, which also requires process ancestry attestation.**

---

### 5. `member_request_scope` deeper detail

When `X-Session-Key` IS provided (e.g., by a legitimate MCP stdio server), `session_key_is_attested` is called. This function does kernel-level AF/UNIX peer credential checking — it confirms the session key belongs to the calling process's ancestry. An external caller with X-Internal-Secret but a forged `X-Session-Key: dashboard:member-raven` would fail `session_key_is_attested` and return `MemberScope(session="dashboard:member-raven", verified=False, store=None)`. The `verified=False` then causes `internal_memory_scope` to return the 409 refusal.

---

## Summary Table

| Caller has | parent_session | Result |
|---|---|---|
| X-Internal-Secret only | "dashboard:member-raven" | **409 member_identity_unavailable** |
| X-Internal-Secret only | "" | **409 member_identity_unavailable** (scope.session=None ≠ "") |
| X-Internal-Secret + valid X-Session-Key (attested) | matching session | **Passes, spawns into that session's store** |
| X-Internal-Secret + forged X-Session-Key | anything | **409** (verified=False) |
| Host CLI (no X-Session-Key, no parent_session, local_owner_bootstrap passes) | "" | **Passes, spawns into Global store** |

---

## Conclusion

**Angle C does not enable routing into a member DM slot.** An external caller bearing only `X-Internal-Secret` and `parent_session="dashboard:member-raven"` is refused with a 409 at `internal_memory_scope` before any member routing occurs. The attestation gate (`session_key_is_attested` via AF/UNIX peer credentials) is not bypassable by the `X-Internal-Secret` header alone.

The one weakness worth noting: with no `X-Session-Key` and no `parent_session`, `member_request_scope` returns `verified=True` with `session=None` and `store=None` — the session-less internal caller is considered "verified" as a no-identity caller. This is intentional design (the host CLI path) but means the `claimed_session=None` bypass (the host_cli path) resolves to Global store, not any member slot.

