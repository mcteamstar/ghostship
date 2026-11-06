# Design

## Context

See proposal.md — Why for motivation.

The current credential store writes one JSON envelope per backend at
`DATA_DIR/credentials/<backend>.json`. `CredentialStore.get/put/delete` take only
`backend`. The module-level singleton `store = CredentialStore("/data")` is imported
by `login.py` (as `_cred_store`) and `tools.py` (as `_cred_store`).

The `LoginFlow` singletons (`KIRO_FLOW`, `CLAUDE_FLOW`, `CODEX_FLOW`) hold one
pending-flow dict at a time. The pending dict is consulted by `launch` (tools.py)
to poll in-flight device flows.

At `launch` time, `_cred_store.get(backend)` resolves the single credential;
the result is injected into the container env and the crew registry entry records
`acp_backend`. Post-login injection in `_handle_login_get` et al. iterates
`registry._reg["crews"]` and injects into all running crews of the matching backend.

The `ghostship auth login/logout/status` CLI functions call HTTP routes with no
profile concept.

**Key constraints:**
- `CredentialStore` is the sole owner of credential files; no other module writes
  them directly.
- All writes are atomic (temp-file + fsync + os.replace); the profile feature must
  maintain this property.
- The `_cred_store.status()` method is called by several HTTP handlers expecting a
  `{backend: {configured, method, stored_at, provider}}` shape; callers must not
  silently break.
- No breaking changes to `CredentialStore.get/put/delete` signatures where called
  with positional args only (the `profile` param is added as a keyword argument with
  default `"default"`).

## Goals / Non-Goals

**Goals:**
- Multiple named profiles per backend can coexist in the credential store.
- Existing single-credential installations work without any operator action (lazy
  migration).
- `launch` can target a specific profile; the profile is recorded in the registry.
- Post-login injection is scoped to the profile used at launch.
- `ghostship auth login/logout/status` expose `--profile` and show all profiles.
- All new public API surfaces are backward-compatible (omitting `profile` behaves
  exactly as today).

**Non-Goals:**
- Multi-backend crew support (each crew still has exactly one backend + profile).
- Profile-level access control or per-profile API keys.
- Concurrent device flows for different profiles of the same backend (the existing
  one-flow-at-a-time constraint is kept; profile is just recorded in the pending dict
  so the credential is written to the right slot on completion).

## Decisions

### D1 — Directory layout: `credentials/<backend>/<profile>.json`

**Chosen:** subdirectory per backend, one file per profile.

**Alternatives considered:**
- `credentials/<backend>--<profile>.json` (flat with separator): simpler dir creation
  but fragile — profile names could theoretically contain the separator; also harder
  to enumerate profiles cleanly.
- `credentials/<backend>.json` with embedded profile dict: would require re-encoding
  existing files and makes atomic partial-profile writes harder. A crash mid-write
  could corrupt all profiles at once.

**Rationale:** The subdirectory layout makes `list_profiles` a simple `os.scandir`,
keeps atomic replace per-profile, and mirrors how the rest of the store works.

### D2 — Backward-compat migration: lazy on `_path()` access, not at startup

**Chosen:** `_migrate_flat_file(backend)` is called inside `_path()` when a flat file
exists. It moves `credentials/<backend>.json` → `credentials/<backend>/default.json`
using `os.replace` (atomic on same filesystem). This happens once per backend, at
first post-upgrade access.

**Alternatives considered:**
- Explicit migration step called by the transport at startup: would require changing
  server.py and adding a startup migration hook that's hard to test in isolation.
- Read-through fallback (check flat file when profile file missing): keeps the flat
  file alive, complicates `list_profiles`, never fully migrates.

**Rationale:** Lazy migration is self-contained in `CredentialStore`, requires no new
startup wiring, is idempotent, and is easy to unit test.

### D3 — `status()` backward compat: keep current shape, add `status_all()`

**Chosen:** `status(profile="default")` keeps the existing `{backend: {...}}` shape,
operating on the named profile. `status_all()` returns the new
`{backend: {profile: {...}}}` shape. Callers that already use `status()` without a
profile arg continue to see exactly the same data.

**Alternatives considered:**
- Change `status()` to always return profile-keyed data: breaks all callers
  (`_handle_login_kiro_get` etc.) without modifying them, introduces a silent data
  shape regression in `test_status_contains_no_values`.
- Deprecate `status()` entirely: requires touching every caller in the same PR,
  expanding scope.

**Rationale:** Adding `status_all()` is strictly additive. The callers that need all
profiles (HTTP `/profiles` routes, `ghostship auth status`) call `status_all()`;
existing single-profile paths call `status(profile)` or `status()`.

### D4 — Profile in `LoginFlow._pending` dict; no second singleton set

**Chosen:** `pending["profile"]` records the target profile for an in-flight device
flow. `write_auth` and `_store()` closures read `pending.get("profile", "default")`
to resolve the destination. `KiroLoginFlow.initiate()` gains a `profile` keyword
argument passed into `pending_extra`.

**Alternatives considered:**
- A new `LoginFlow` subclass per profile: explosion of singletons; fundamentally no
  more than one device flow is in flight per backend at a time anyway.
- A `profile` field on the `LoginFlow` class: not thread-safe (two callers could set
  it before either flow completes).

**Rationale:** The pending dict is already the per-flow state bag. Adding `profile`
there is the minimal, thread-safe extension.

### D5 — `launch` implicit profile resolution order

**Chosen:**
1. If `profile` is explicitly specified and non-empty → use it.
2. Else if exactly one profile exists for the backend → use that profile implicitly.
3. Else → use `"default"`.

If implicit or explicit resolution yields a profile with no stored credential, the
existing `not_authenticated` path fires (with the resolved profile name in the message
for disambiguation).

**Alternatives considered:**
- Always require `profile` when multiple profiles exist: breaks existing callers that
  rely on `launch` being credential-agnostic.
- Fail loudly when multiple profiles exist and none is `default`: too disruptive for
  operators with a single non-default profile who upgrade from single-cred state.

**Rationale:** The spec says "if only one profile exists it is used implicitly" and
"default profile name is default". Rule 2 handles the "I have one profile named
`corp`" case; rule 3 is the safe fallback.

### D6 — `acp_profile` in crew registry; post-login injection filtered by it

**Chosen:** At `launch`, after resolving the profile, `registry._reg["crews"][crew_id]`
is written with `"acp_profile": resolved_profile` alongside `"acp_backend"`. In
`_handle_login_get` (and the claude/codex equivalents), the running-crew iteration
filters on both `acp_backend` and `acp_profile` matching the profile in `pending`.

Legacy crew entries without `acp_profile` default to `"default"` at read time
(same pattern as `acp_backend` defaulting to `"kiro"`).

**Alternatives considered:**
- Inject into all crews of the backend regardless of profile (simplest, safe for
  now): would mean a `corp` login refreshes credentials in a `default` crew — wrong
  credential injected silently.

**Rationale:** Correctness. Injecting the wrong profile's credential into a running
crew would cause that crew's subsequent requests to fail.

### D7 — HTTP profile param: query string for GET/logout, JSON body for login POST

**Chosen:**
- `GET /login/<backend>?profile=<name>` — query param.
- `GET /login/<backend>/profiles` — new route, no param needed.
- `POST /login/<backend>/<method>` — `profile` in JSON body alongside `secret` (or
  alongside flow-specific fields like `start_url`/`region`).
- `POST /logout/<backend>?profile=<name>` — query param (body may be empty `{}`).

**Alternatives considered:**
- Profile in URL path (`/login/kiro/corp/api-key`): breaks the existing route table
  and requires server.py to parse a variable-depth path; also changes a stable URL
  that existing tooling may already call.
- Always in body: logout sends an empty body today; adding a required parse step for
  an optional param is awkward.

**Rationale:** Query params for read-only/stateless operations (GET status, POST
logout) are conventional; JSON body for login POST is consistent with how `secret`
and `start_url`/`region` are already passed.

### D8 — Reserved `"default"` name: `allow_default` flag on `_validate_profile`

**Chosen:** `_validate_profile(profile: str, allow_default: bool = False) -> None` gains
a boolean keyword argument. When `allow_default=False` (the default), passing `"default"`
raises `ValueError("'default' is a reserved profile name and may not be supplied explicitly")`.
When `allow_default=True`, `"default"` passes validation unchanged. Internal call sites that
legitimately write the default profile — `_migrate_flat_file` and the `_resolve_profile`
fallback in `tools.py` — call `_validate_profile(profile, allow_default=True)`. All
user-facing call sites (HTTP handler POST-body reads, query-param reads, ghostship CLI arg
parsing) use the default `allow_default=False`; they catch `ValueError` and return HTTP 400
(CLI: user-visible error message).

**Alternatives considered:**
- A separate `_path_internal(backend, profile)` that skips validation entirely: would
  duplicate the path-construction logic and make it easier to accidentally bypass validation
  for non-internal callers.
- Two separate functions `_validate_profile_user` / `_validate_profile_internal`: naming
  overhead; a single function with a flag keeps the logic in one place and is a
  well-established pattern.

**Rationale:** A single function with a boolean keyword flag is the minimal change: the
caller's intent is explicit, the validation logic is not duplicated, and the default
(`allow_default=False`) means any new user-facing call site that omits the flag
automatically enforces the reserved-name check without extra thought.

## Risks / Trade-offs

[Risk: Lazy migration is per-process and not globally locked] → The credential
directory is local to a single transport process; no concurrent migration race is
expected. If two processes share `DATA_DIR` (unsupported configuration), the worst
case is one migrates while the other reads the flat file — both paths return the same
credential bytes.

[Risk: `profile` param on `LoginFlow.initiate` changes a method signature used in
`lifecycle.py`] → Reviewed: `_initiate_login` in `lifecycle.py` calls
`KIRO_FLOW.initiate(podman, method=…, provider=…)` — the new `profile` keyword
argument has a default, so the call site does not need updating. Verify in
`lifecycle.py` before closing the task.

[Risk: Existing `test_credentials_store.py` tests call `put/get/delete/status` with
positional args] → All new parameters are keyword-only with defaults; existing test
calls remain valid.

[Risk: `acp_profile` absent from pre-TRN-252 registry entries] → Defaulted to
`"default"` at read time (same pattern as `acp_backend`); no migration needed.

[Risk: ghostship CLI hand-written arg parser] → The existing `auth_login`,
`auth_logout`, `auth_status` functions parse `args: list[str]` manually; the
`--profile` flag follows the same pattern as `--method`, `--region`, etc. already
present. No parser library to introduce.

## Migration Plan

1. Deploy new transport binary. On first credential access, the lazy migration moves
   `credentials/<backend>.json` → `credentials/<backend>/default.json` atomically.
2. All existing `launch` calls without `profile` resolve to `default`, matching the
   migrated file — zero disruption.
3. All existing running crews lack `acp_profile` in their registry entries; they
   receive `default` at read time, which is the correct fallback.
4. No downgrade path is needed: the subdirectory layout is ignored by older binaries
   (they would look for `credentials/<backend>.json` and find nothing, prompting
   re-login) — this is acceptable since the feature adds a new directory.

## Open Questions

None. All ambiguities were resolved by the stated design decisions above.
