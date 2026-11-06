# Tasks

## 1. CredentialStore — profile-aware schema and migration

- [ ] 1.1 Add `_PROFILE_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$")` and
  `_validate_profile(profile: str) -> None` to `transport/credentials.py`. Verify
  `_validate_profile("default")` passes, `_validate_profile("corp")` passes, and
  `_validate_profile("Bad-Profile")` raises `ValueError`.

- [ ] 1.2 Rewrite `CredentialStore._path(backend, profile="default") -> Path` to return
  `self._dir / backend / f"{profile}.json"`. Add
  `_migrate_flat_file(backend: str) -> None` that atomically moves
  `self._dir / f"{backend}.json"` → `self._dir / backend / "default.json"` (via
  `os.replace`) when the flat file exists and the profile file does not; when both
  exist, removes the flat file and keeps the profile file. Call `_migrate_flat_file`
  at the start of every public method that resolves a path for the `"default"` profile.
  Update `_ensure_dir()` to create `self._dir / backend /` with mode 0700.
  Verify the old flat `credentials/kiro.json` is absent and
  `credentials/kiro/default.json` contains the same bytes after first access.

- [ ] 1.3 Update `get(backend, profile="default") -> dict | None` to pass `profile` to
  `_path`. Add `_validate_profile(profile)` call. Verify `get("kiro", profile="corp")`
  returns `None` when only `kiro/default` exists.

- [ ] 1.4 Update `put(backend, method, payload, provider=None, profile="default") -> None`
  to pass `profile` to `_path` and `_ensure_dir` (which now creates the
  per-backend subdirectory). Add `_validate_profile(profile)` call before `_validate`.
  Verify two distinct files are written for `put("kiro", "api-key", "k1", profile="default")`
  and `put("kiro", "api-key", "k2", profile="corp")`, each with mode 0600 and directory
  with mode 0700.

- [ ] 1.5 Update `delete(backend, profile="default") -> bool` to pass `profile` to `_path`.
  Verify `delete("kiro", profile="corp")` removes only `kiro/corp.json` and leaves
  `kiro/default.json` untouched.

- [ ] 1.6 Add `list_profiles(backend: str) -> list[str]` to `CredentialStore`. It should
  scan `self._dir / backend /` with `os.scandir`, collect `.json` file stems (filenames
  without extension), and return a sorted list. Returns `[]` when the directory does not
  exist or is empty. Verify it returns `["corp", "default"]` after storing two profiles.

- [ ] 1.7 Keep `status(profile="default") -> dict` signature-compatible. Internally it should
  call `get(backend, profile)` for each backend and build the same
  `{backend: {configured, method, stored_at, provider}}` shape as before. Existing test
  `test_status_contains_no_values` must still pass without modification.

- [ ] 1.8 Add `status_all() -> dict[str, dict[str, dict]]` to `CredentialStore`. For each
  backend, call `list_profiles(backend)` and call `status(profile)` for each; build
  `{backend: {profile: status_dict}}`. Returns `{backend: {}}` when no profiles exist
  for a backend. No payload or secret value may appear. Verify:
  after storing `kiro/default` and `kiro/corp`, `status_all()["kiro"]` has two keys.

- [ ] 1.9 Update `tests/unit/test_credentials_store.py`:
  - Extend `test_file_mode_0600_and_dir_0700` to check `credentials/claude/default.json`
    mode 0600 and `credentials/claude/` mode 0700.
  - Add `test_profile_isolation`: put `kiro/default` and `kiro/corp`; verify `get` for
    each returns the correct payload; verify `delete("kiro", profile="corp")` leaves
    `kiro/default` intact.
  - Add `test_lazy_migration`: write a flat `credentials/kiro.json`; call `get("kiro")`;
    verify `credentials/kiro/default.json` now exists, `credentials/kiro.json` is gone,
    and the returned payload matches.
  - Add `test_list_profiles_sorted` and `test_list_profiles_empty`.
  - Add `test_status_all_two_profiles` and `test_status_all_empty_backend`.
  - Add `test_validate_profile_accepts_valid` and `test_validate_profile_rejects_invalid`.
  - Verify `python -m pytest tests/unit/test_credentials_store.py` exits 0.

## 2. LoginFlow — profile in pending state and HTTP handlers

- [ ] 2.1 Add `profile: str = "default"` keyword argument to `KiroLoginFlow.initiate(podman,
  method=None, provider=None, profile="default")`. Pass `{"profile": profile}` inside
  `pending_extra` when calling `super().initiate(podman, pending_extra=...)`. No change
  to the ABC `initiate` signature. Verify that `KIRO_FLOW.state["profile"] == "corp"`
  after calling `KIRO_FLOW.initiate(podman, profile="corp")` (with the flow immediately
  aborted to avoid a real container start; mock `start_container`).

- [ ] 2.2 Add `profile: str = "default"` keyword argument to `ClaudeLoginFlow.initiate` and
  `CodexLoginFlow.initiate` (both override `initiate` or call `super()`; they must pass
  `profile` through `pending_extra`). Verify `CLAUDE_FLOW._pending["profile"] == "corp"`
  for a mocked flow.

- [ ] 2.3 In `_handle_login_get` (kiro completion handler), inside the `_store()` closure,
  read `profile = pending.get("profile", "default")` and pass it to
  `_cred_store.put("kiro", _method, ..., profile=profile)`. In the post-completion
  running-crew injection loop, add a filter:
  `info.get("acp_profile", "default") == profile` alongside the existing
  `acp_backend == "kiro"` filter. Verify: a crew registered with `acp_profile="corp"`
  is injected when the kiro/corp flow completes; a crew with `acp_profile="default"`
  is not.

- [ ] 2.4 Apply the same profile-aware `_store()` and injection filter changes to
  `_handle_claude_login_get` for the claude backend. Verify analogously.

- [ ] 2.5 Apply the same profile-aware `_store()` closure change to
  `_handle_codex_login_get`. (Codex does not inject into running crews at completion
  time beyond the credential write, but the store call must record the profile.)

- [ ] 2.6 Update all pasted-secret POST handlers to read `profile` from the JSON body
  (defaulting to `"default"`) and call `_validate_profile(profile)` (returning 400 on
  invalid name) before calling `_cred_store.put(..., profile=profile)`:
  `_handle_login_kiro_api_key_post`, `_handle_login_claude_api_key_post`,
  `_handle_login_claude_setup_token_post`, `_handle_login_codex_api_key_post`.
  Update all device-flow POST handlers similarly:
  `_handle_login_kiro_builder_id_post`, `_handle_login_kiro_identity_center_post`,
  `_handle_login_claude_oauth_post`, `_handle_login_codex_chatgpt_post` — pass profile
  to `_handle_login_post` / `CLAUDE_FLOW.initiate` / `CODEX_FLOW.initiate`.
  Verify: `POST /login/kiro/api-key {"secret": "k", "profile": "corp"}` stores under
  `kiro/corp`; omitting `profile` stores under `kiro/default`.

- [ ] 2.7 Update `_handle_login_kiro_get`, `_handle_login_claude_get_new`,
  `_handle_login_codex_get_new` to extract `profile` from the query string
  (`request.query_params.get("profile", "default")`), validate it, and pass it to
  `_cred_store.status(profile)`. Return 400 on invalid profile name.
  Verify: `GET /login/kiro?profile=corp` returns `configured: false` when `kiro/corp`
  is absent; returns `configured: true` when it exists.

- [ ] 2.8 Add three new handlers — `_handle_login_kiro_profiles_get`,
  `_handle_login_claude_profiles_get`, `_handle_login_codex_profiles_get` — each
  calling `_cred_store.list_profiles(backend)` and returning
  `JSONResponse({"profiles": sorted_list})`. Register them in `transport/server.py`
  route table as `("GET", "/login/kiro/profiles")`, `("GET", "/login/claude/profiles")`,
  `("GET", "/login/codex/profiles")` and import the handlers.
  Verify: after storing `kiro/default` and `kiro/corp`, `GET /login/kiro/profiles`
  returns `{"profiles": ["corp", "default"]}`.

- [ ] 2.9 Update `_logout(backend, request)` to read `profile` from the request query
  string (`request.query_params.get("profile", "default")`), validate it (400 on
  invalid), and pass `profile` to `_cred_store.delete(backend, profile)`. Also check
  that any in-progress flow's `_pending.get("profile", "default") == profile` before
  aborting (only abort the flow if it matches the targeted profile, or if no profile
  information is present in the pending state). Update the three logout handler wrappers
  (`_handle_logout_kiro_post`, `_handle_logout_claude_post_new`,
  `_handle_logout_codex_post_new`) to pass `request` to `_logout`.
  Verify: `POST /logout/kiro?profile=corp` removes only `kiro/corp`; `POST /logout/kiro`
  (no param) removes `kiro/default`.

- [ ] 2.10 Update `tests/unit/test_credentials_routes.py`:
  - Add a `TestProfileParam` test class: verify that posting with `profile="corp"` stores
    under `corp` for each backend/method; verify omitting `profile` stores under `default`.
  - Add `TestProfilesRoute`: verify `GET /login/{backend}/profiles` returns sorted list,
    returns `[]` when empty.
  - Add `TestProfileTargetedLogout`: verify `POST /logout/kiro?profile=corp` leaves
    `kiro/default` in the store; verify invalid profile name returns 400.
  - Verify `python -m pytest tests/unit/test_credentials_routes.py` exits 0.

- [ ] 2.11 In `tests/unit/test_credentials_routes.py` (or a new
  `tests/unit/test_login_flow_profile.py`), add a test that:
  1. Starts a kiro device flow with `profile="default"` (mock the flow initiation so no
     real container starts).
  2. Calls `POST /logout/kiro?profile=corp`.
  3. Verifies the in-flight `default` flow is NOT aborted — i.e. `KIRO_FLOW._pending`
     still contains the flow state for the `default` profile.
  4. Verifies only `kiro/corp` is targeted for deletion (even if absent, no error is
     raised).

## 3. launch — profile selection and registry

- [ ] 3.1 Add `profile: str | None = None` to the `launch` function signature in
  `transport/tools.py`. Implement `_resolve_profile(backend: str, requested: str | None,
  store: CredentialStore) -> str` helper at module level: returns `requested.strip()`
  if non-empty; else if `len(store.list_profiles(backend)) == 1` returns that profile;
  else returns `"default"`. Call `_validate_profile(resolved_profile)` (return
  `{"error": "invalid profile name"}` if invalid).
  Verify `_resolve_profile("kiro", "corp", store)` returns `"corp"`;
  `_resolve_profile("kiro", None, store)` returns `"corp"` when only `kiro/corp`
  exists; returns `"default"` when `kiro/default` and `kiro/corp` both exist.

- [ ] 3.2 Replace `_cred = _cred_store.get(backend)` in the auth-gating block with
  `_cred = _cred_store.get(backend, resolved_profile)`. The remainder of the gating
  logic (flow initiation, `_kiro_api_key` extraction, `auth_b64` resolution, kiro poll
  path) remains structurally the same but now operates on the resolved profile.
  For the kiro-poll `commit_if_current` call, pass `profile=resolved_profile` to
  `_cred_store.put`.
  Verify: `launch(crew_id="c", backend="kiro", profile="corp")` with only `kiro/corp`
  stored passes auth gating; with only `kiro/default` stored it triggers a login flow.

- [ ] 3.3 In the registry pre-insert placeholder and in the `_finish_crew_setup` kwargs
  dict, add `"acp_profile": resolved_profile`. The existing `_finish_crew_setup`
  signature is unchanged — it receives `**kwargs`; `backend` is passed as a kwarg
  already (see tools.py line 1117). Add `acp_profile` to that same call.
  Inside the `_finish_crew_setup` call result path, also ensure the placeholder entry
  written before the try-block includes `"acp_profile": resolved_profile`.
  Verify: after a successful `launch`, `registry._reg["crews"][crew_id]["acp_profile"]`
  equals the resolved profile.

- [ ] 3.4 In `_build_crews_payload` and `_build_internal_fleet_payload`, add
  `"acp_profile": info.get("acp_profile", "default")` to each `entry` dict alongside
  `"acp_backend"`. Verify `crews()` output includes `acp_profile` for each crew entry;
  a legacy entry without `acp_profile` shows `"default"`.

- [ ] 3.5 In `lifecycle.py`, verify that `_initiate_login(podman, method=..., provider=...)`
  call sites do not need updating (the new `profile` kwarg on `KiroLoginFlow.initiate`
  defaults to `"default"`, and `_initiate_login` is a wrapper around `KIRO_FLOW.initiate`).
  If `_initiate_login` forwards to `KIRO_FLOW.initiate`, add `profile` forwarding.
  Verify: `_initiate_login(podman, method="builder-id")` works unchanged; a test mock
  confirms `KIRO_FLOW._pending.get("profile") == "default"` in this path.

- [ ] 3.6 Update `tests/unit/test_launch_backend.py`:
  - Add `test_explicit_profile_selects_credential`: store `kiro/corp`; `launch(backend="kiro",
    profile="corp")` must not start a login flow and must pass `acp_profile="corp"` to
    `_finish_crew_setup`.
  - Add `test_implicit_single_profile`: store only `kiro/corp` (no `kiro/default`);
    `launch(backend="kiro")` with no `profile` must select `corp` implicitly.
  - Add `test_missing_named_profile_triggers_auth`: store `kiro/default`; `launch(backend="kiro",
    profile="corp")` must return `not_authenticated`.
  - Add `test_acp_profile_in_registry`: after a successful launch, confirm the crews dict
    entry contains the correct `acp_profile`.
  - Add `test_crews_output_includes_acp_profile`: mock two registry entries with different
    `acp_profile` values; confirm `crews()` output includes them.
  - Verify `python -m pytest tests/unit/test_launch_backend.py` exits 0.

## 4. Server route registration

- [ ] 4.1 In `transport/server.py`, import `_handle_login_kiro_profiles_get`,
  `_handle_login_claude_profiles_get`, `_handle_login_codex_profiles_get` from
  `transport.login`. Add them to both the primary `routes` dict and the
  `public_routes_no_key` dict:
  `("GET", "/login/kiro/profiles")`, `("GET", "/login/claude/profiles")`,
  `("GET", "/login/codex/profiles")`. Verify by running
  `python -m pytest tests/unit/test_credentials_routes.py -k profiles` — all profile
  route tests pass.

## 5. ghostship CLI — profile flags

- [ ] 5.1 In `auth_login(args)` in `ghostship`, parse `--profile` using the same
  manual-index pattern as `--method`: `profile = "default"` if `"--profile"` not in
  args, else `args[args.index("--profile") + 1]`. For pasted-secret methods, include
  `"profile": profile` in the POST body alongside `"secret"`. For device-flow methods,
  include `"profile": profile` in the `request_body` dict. Update `_AUTH_USAGE` to
  document `[--profile <name>]` for `login` and `logout`.
  Verify: `ghostship auth login kiro --method api-key --profile corp` sends a POST body
  containing `"profile": "corp"` (inspectable by intercepting the HTTP call in a test).

- [ ] 5.2 In `auth_logout(args)` in `ghostship`, parse `--profile` and append
  `?profile=<name>` to the `/logout/{backend}` URL when specified (default: `"default"`).
  Always append the param so the route knows the exact target.
  Verify: `ghostship auth logout kiro --profile corp` calls `POST /logout/kiro?profile=corp`.

- [ ] 5.3 Rewrite `auth_status(args)` in `ghostship` to:
  1. For each backend in `_VALID_BACKENDS`, call `GET /login/{backend}/profiles`.
  2. For each returned profile name, call `GET /login/{backend}?profile=<p>`.
  3. In `--json` mode, emit `{backend: {profile: status_dict, ...}}`.
  4. In human mode, print each backend as a section header, then each profile as an
     indented entry showing `method`, `configured`, and `stored_at`.
  Verify: with two kiro profiles stored, `ghostship auth status` human output shows
  both; `--json` output is valid JSON with the two-level structure.

## 6. Integration verification

- [ ] 6.1 Run `openspec validate --change multi-profile-credentials` and confirm it exits 0
  with no errors.

- [ ] 6.2 Run the full unit test suite: `python -m pytest tests/unit/` and verify exit 0.
  Confirm all pre-existing tests in `test_credentials_store.py`, `test_credentials_routes.py`,
  `test_credentials_launch.py`, and `test_launch_backend.py` still pass without modification
  to their existing test methods.

- [ ] 6.3 Perform a backward-compatibility smoke check: construct a `CredentialStore` instance,
  call `put("claude", "api-key", "sk-ant-x")` with no `profile` arg, then call
  `get("claude")` with no `profile` arg. Confirm the payload is returned correctly
  (default-profile path).

- [ ] 6.4 In `transport/login.py`, audit every `_handle_login_*_get` handler that calls
  `_cred_store.status()` and returns its output in an HTTP response body. Confirm none
  of them expose the `profile` keyword argument unexpectedly or break existing callers.
  Add an inline comment at each call site where `status(profile=...)` is invoked (after
  task 2.7 is implemented) to make the intent explicit — e.g.
  `# profile scoped to the query-param value, defaults to "default"`.
  Verify: existing `test_credentials_routes.py` GET status tests still pass unchanged
  after tasks 1.7 and 2.7 are implemented.

## Workflow follow-up

- After review is complete, have Ghost implement the change.
- Archive after implementation is verified.
