# Test Suite Audit — tests/unit/

**Date:** 2026-10-15  
**Auditor:** Banshee (TRN-244)  
**Baseline:** 1355 passed, 2 skipped, 127 s (bash tests/run.sh --unit)

---

## 1. File inventory — what each file tests

| File | Tests | Lines | What it tests |
|------|------:|------:|---------------|
| `test_server.py` | 177 | 4254 | Main transport server: proxy handlers, login/logout, dispatch, schedule, captain jobs, policy injection, model override, config patching, pickup, version, OpenAPI, CSP, WS, broadcast, auth |
| `test_captain.py` | 110 | 2545 | Captain sentinel: standing orders, cron scheduling, stop/resume, mail reading, cookie injection, subject reader |
| `test_lifecycle.py` | 87 | 3128 | Lifecycle: `_ensure_crew_running`, `_launch`, `_nuke`, reconcile loop, active-crew limit, memory gate, setup, copy agents, prewarm triggers |
| `test_monitors.py` | 77 | 2439 | Idle monitor, schedule monitor, cron/one-shot activity checks, cookie refresh on 401/403, double-stop prevention |
| `test_caddy.py` | 68 | 1574 | Caddy register/deregister, dashboard login POST, session auth, launch/nuke, REST endpoints |
| `test_auth.py` | 57 | 955 | Bearer auth middleware, HMAC token signing/verification, evac/supply token modes, file get/put validation |
| `test_academy.py` | 46 | 810 | Crew type registry, manifest helpers, image resolution, launch with composition, env-var substitution, agent copy, prewarm trigger |
| `test_files.py` | 44 | 1099 | `transport.files`: file GET, bundle upload/download, signing, presigned URLs, URL base resolution, worker helpers |
| `test_openapi.py` | 42 | 606 | OpenAPI schema generation, route list, response types |
| `test_ghostship_auth.py` | 41 | 473 | CLI auth: URL resolution, API key parsing, HTTP helpers, login flow |
| `test_security.py` | 36 | 456 | Secrets management, credential storage, throttling, sessions, CSP nonce (partial overlap with `test_trn237_csp_nonce.py`) |
| `test_registry.py` | 29 | 728 | Registry: `_advance_next_fire_at`, save durability (fsync, mode 0600, corrupt JSON, race), write_crew_secret, batch find |
| `test_hardening.py` | 29 | 930 | Admiral key injection, crew JSON hygiene, container hardening flags, file transfer audit events, API key loading, login concurrency |
| `test_config_from_env.py` | 27 | 220 | `Config.from_env`: int/float validation, valid values, defaults, base image, prewarm, TLS |
| `test_recovery.py` | 26 | 732 | Probe gateway, refresh cookie, crew API with recovery (stale cookie, connection error, double failure), error messages |
| `test_rate_limiting.py` | 24 | 359 | Rate limiter record, thread safety, middleware pass/block, path matching, exempt paths |
| `test_podman.py` | 24 | 418 | Podman client: memory gate (cache, disabled), container state errors, secret helpers |
| `test_agent_backends.py` | 24 | 252 | `parse_agent_backends`: parsing, kiro always-on, default backend, deprecated alias, retired flags, inert settings, login gating |
| `test_batch.py` | 23 | 391 | Batch CRUD (registry), dispatch guard, pickup (lost member, timeout, done), status update |
| `test_network.py` | 21 | 308 | Podman network helpers, DNS, bridge mode |
| `test_file_transfer.py` | 21 | 770 | Podman archive primitives, upload regressions (raw, archive, bundle), download regressions, evac unpack signing; also hosts the original `_install_import_stubs` shim |
| `test_trn167_claude_backend.py` | 20 | 422 | Claude/ACP backend config validation, config patching, finish_crew_setup auth branch, launch kiro-auth skip |
| `test_trn225_memory_pressure.py` | 18 | 263 | `_check_in_memory_pressure`, `_is_memory_pressure_refusal`, `_record_memory_pressure_cycle` |
| `test_container_scripts.py` | 18 | 302 | Container scripts: inject_auth, read_auth, wipe_auth, read_mail_counts, read_mail_subjects, patch_models, inject_policy |
| `test_prewarm.py` | 17 | 413 | Prewarm: core flow, memory gate, active-crew gate, TTL, implicit triggers (supply, schedule) |
| `test_ghostship_cli.py` | 17 | 276 | CLI: stop, status, setup commands |
| `test_streaming_transfer.py` | 16 | 205 | `ResponseChunkReader`, `TarMemberStream`, transfer upload slash-ref |
| `test_admiral_sig.py` | 16 | 478 | `verify-admiral-sig`: valid/invalid signatures, hardening defects, signer/verifier integration, whitespace boundary keys |
| `test_trn237_csp_nonce.py` | 15 | 314 | CSP nonce middleware threading, login page stamping, end-to-end consistency (enforced, no unsafe-inline) |
| `test_crew.py` | 15 | 160 | `Crew` dataclass: round-trip, dict shape, gateway URL, cookie header, is_idle, is_warm |
| `test_version.py` | 14 | 196 | Transport version read, version endpoint, crews version field, container inspect, resource version, Containerfile |
| `test_podman_exec_stdin.py` | 14 | 478 | `container_exec_stdin` HTTP/101 handshake, stdin forwarding, exit code; also Podman error paths (secret, volume, network ops) |
| `test_dashboard_session.py` | 14 | 266 | TTL/JWT helpers, UI proxy cookie injection, strip/refresh, Caddy-to-transport routing, WS relay |
| `test_launcher.py` | 13 | 517 | Concurrent restart serialisation, active limit gate, memory gate, nuked sentinel, finish_setup |
| `test_dispatch_slot.py` | 12 | 258 | Dispatch slot assignment: enrolled/unenrolled, None/False/True override, batch member/headless |
| `test_agent_backends_parity.py` | 11 | 137 | Parity between Python and shell `agent_backends` parsers, toolchain list, robustness |
| `test_ws_proxy.py` | 10 | 409 | WS proxy: missing dependency, resolve failure, upstream failure, bidirectional relay, cookie refresh |
| `test_trn171_anthropic_endpoint_override.py` | 10 | 312 | Anthropic base URL injection in container env for Claude vs kiro backend, config read |
| `test_trn157_lifecycle_race_keypair.py` | 9 | 430 | Generation-counter race guard, `_finish_crew_setup` cookie cleanup, launch registry cleanup |
| `test_trn231_require_api_key.py` | 7 | 73 | `_enforce_require_api_key` startup gate (loopback/non-loopback, error/off/warn modes) |
| `test_trn222_ws_auth_invariants.py` | 7 | 191 | WS proxy no X-App-Token, `DashboardGate.handle_auth` reads only gs_session cookie |
| `test_review_quick_fixes.py` | 7 | 73 | Next-URL backslash redirect, NaN/inf float rejection, backend list line-break rejection |
| `test_tls.py` | 6 | 157 | TLS gating, context factory (cert/key, min version, missing cert) |
| `test_dashboard_default.py` | 6 | 66 | `dashboard_default` config resolution |
| `test_trn235_config_repr_masking.py` | 5 | 72 | `Config.__repr__` secret masking |
| `test_trn156_lifecycle_memory_cron.py` | 5 | 273 | `_task_timestamps` TTL eviction, `_warm_markers` eviction, one-shot registry-first disablement |
| `test_auth_failure_reporting.py` | 5 | 120 | Login/logout write-failure reporting (500 path, audit trail) |
| `test_trn226_claude_setup_token_removed.py` | 4 | 44 | Guardrail: `POST /login/claude/setup-token` route permanently removed |
| `test_trn223_knowledge_autoingest.py` | 4 | 185 | No implicit knowledge auto-ingest in full_overrides, upstream default opt-in |
| `test_trn220_crew_api_headers.py` | 4 | 89 | `_crew_api` header invariant: only Cookie+Origin, no X-Internal-Secret or X-Session-Key |
| `test_trn241_crew_id_env.py` | 3 | 58 | `KIROCREW_CREW_ID` injected into container env |
| `test_trn_221_no_hardcoded_sel_path.py` | 1 | 56 | Static-analysis guard: no hardcoded SEL key path in transport/ |
| `test_seed_kiro_db.py` | 1 | 157 | `seed_kiro_db.py` migration count (slow, requires podman) |
| `test_config_sync.py` | 1 | 43 | Every `Config` field has an entry in `ghostship.conf.example` |
| `test_maildeliver.sh` | — | 134 | Shell: `maildeliver`/`sendmail-local` recipient validation (BASE allowlist) |
| `test_trn227_compose_retry.sh` | — | 135 | Shell: compose retry-on-failure logic |

---

## 2. Files testing the same thing (potential duplicates / overlap)

### 2a. File-transfer split (benign, intentional)

`test_file_transfer.py` and `test_files.py` both cover file/bundle transfer but target different layers:
- `test_file_transfer.py` — Podman archive primitives, upload regressions at the `transport.files` call-site, evac unpack signing.  Also the historical home of `_install_import_stubs` (now delegated to `_stubs.py`).
- `test_files.py` — Higher-level file-GET, bundle upload/download tool logic, URL signing, presigned URL base resolution, worker helpers.

These two are **complementary, not duplicate** — but they share a purpose (`transport.files`) and could be merged into one authoritative `test_files.py`. Not urgent; no overlap defect.

### 2b. Memory pressure covered in multiple files

`test_trn225_memory_pressure.py` tests `server._check_in_memory_pressure`, `_is_memory_pressure_refusal`, `_record_memory_pressure_cycle` as isolated unit tests.  
`test_lifecycle.py::MemoryGateDisabledTests` and `test_launcher.py::TestMemoryGate` test the same gate at the lifecycle/launcher call-site.  
`test_podman.py` tests the Podman-level gate (memory cache).  
**Verdict:** complementary layering, not duplication — each tests a different integration level.

### 2c. Claude/Anthropic backend split

`test_trn167_claude_backend.py` and `test_trn171_anthropic_endpoint_override.py` both test the Claude ACP backend path. The split is clean (config validation + auth branch vs. ANTHROPIC_BASE_URL env injection). Some config tests in `test_trn167` (`TestAcpBackendConfigValidation`) partially overlap with `test_agent_backends.py::TestDeprecatedAlias` and `TestRetiredFlags`. **Not a meaningful duplicate** — different specificity.

### 2d. CSP nonce in two files

`test_trn237_csp_nonce.py` (15 tests) covers nonce middleware and login page stamping.  
`test_security.py::TestCspNonce` (7 tests) covers nonce generation, uniqueness, length.  
**Verdict:** complementary — `test_security.py` tests the generator primitive; `test_trn237` tests the middleware wiring. No duplicate removal warranted.

### 2e. Agent-backends parser tested twice

`test_agent_backends.py` (24 tests) tests `parse_agent_backends` from Python.  
`test_agent_backends_parity.py` (11 tests) tests parity between Python and shell parsers, shell robustness, toolchain list.  
**Verdict:** intentionally different concerns — parity file is a cross-cutting contract test.

### 2f. Dashboard session helpers in two files

`test_dashboard_session.py` tests TTL/JWT helpers + proxy cookie injection.  
`test_caddy.py::DashboardLoginPostTests` and `::DashboardAuthTests` test the Caddy-facing login/auth endpoint.  
**Verdict:** complementary layers.

---

## 3. Broken / hanging tests

**None found.** No PTY/select loop patterns were identified in any `.py` test file. The shell tests (`test_trn227_compose_retry.sh`, `test_maildeliver.sh`) are bounded scripts, not polling loops.

`test_seed_kiro_db.py` is marked `@pytest.mark.slow` and `@unittest.skipUnless(shutil.which("podman"), ...)`. It is correctly excluded from the default run (deselected in baseline). Not broken — correctly gated.

`test_trn223_knowledge_autoingest.py` has 2 tests marked skip (`ss` in baseline). These test upstream gateway behaviour and are correctly skipped when the live gateway is unavailable.

---

## 4. Worth keeping vs. deleting

### Keep (all of them, for these reasons)

Every file in this suite tests distinct behaviour:

- **Core transport modules** (`test_server`, `test_lifecycle`, `test_monitors`, `test_caddy`, `test_captain`, `test_registry`, `test_files`, `test_file_transfer`, `test_recovery`, `test_auth`, `test_hardening`, `test_security`, `test_openapi`, `test_academy`, `test_podman`, `test_podman_exec_stdin`, `test_prewarm`, `test_launcher`, `test_batch`, `test_network`, `test_rate_limiting`, `test_ws_proxy`, `test_streaming_transfer`, `test_tls`, `test_crew`, `test_container_scripts`, `test_version`, `test_dispatch_slot`, `test_ghostship_auth`, `test_ghostship_cli`, `test_agent_backends`, `test_agent_backends_parity`, `test_dashboard_session`, `test_dashboard_default`, `test_admiral_sig`): all high-value, cover non-trivial behaviour.

- **Config tests** (`test_config_from_env`, `test_config_sync`): distinct concerns.

- **Auth helper** (`test_auth_failure_reporting`): small but non-redundant.

- **TRN guardrails** — these are *regression guards* pinning behaviour that was previously undefined or incorrectly specified. They remain valuable precisely because they ensure future changes don't silently revert a fix:
  - `test_trn156_lifecycle_memory_cron.py` — TTL eviction bug guard (5 tests)
  - `test_trn157_lifecycle_race_keypair.py` — race/TOCTOU guard (9 tests)
  - `test_trn167_claude_backend.py` — Claude backend correctness (20 tests)
  - `test_trn171_anthropic_endpoint_override.py` — endpoint injection (10 tests)
  - `test_trn220_crew_api_headers.py` — header invariant (4 tests)
  - `test_trn221_no_hardcoded_sel_path.py` — static analysis guard (1 test)
  - `test_trn222_ws_auth_invariants.py` — WS auth invariant (7 tests)
  - `test_trn223_knowledge_autoingest.py` — opt-in posture (4 tests, 2 skip)
  - `test_trn225_memory_pressure.py` — memory pressure helpers (18 tests)
  - `test_trn226_claude_setup_token_removed.py` — route-removal guard (4 tests)
  - `test_trn227_compose_retry.sh` — compose retry shell (bounded)
  - `test_trn231_require_api_key.py` — startup gate (7 tests)
  - `test_trn235_config_repr_masking.py` — secret masking (5 tests)
  - `test_trn237_csp_nonce.py` — CSP nonce wiring (15 tests)
  - `test_trn241_crew_id_env.py` — env injection guard (3 tests)
  - `test_review_quick_fixes.py` — open redirect + float + linebreak guards (7 tests)

- **Slow/infra** (`test_seed_kiro_db.py`): correctly gated with `@pytest.mark.slow`; provides CI value in the slow lane.

- **Shell** (`test_maildeliver.sh`, `test_trn227_compose_retry.sh`): bounded, valid.

### Delete candidates

**None.** No file consists purely of implementation-detail tests, duplicate assertions, hanging loops, or content that belongs elsewhere. The TRN files are named after their originating ticket but each tests real behaviour that has no home in the core module test files; they are not "junk."

---

## 5. Consolidation opportunities (logical groupings)

The suite is already logically grouped by production module. The remaining opportunity is absorbing the smallest TRN files into their natural homes, but the cost (losing the explicit regression-guard doc comment) likely exceeds the benefit for files with fewer than 10 tests. The consolidation below is feasible but advisory:

| Candidate merge | Target | Tests | Notes |
|-----------------|--------|------:|-------|
| `test_trn226_claude_setup_token_removed.py` | `test_lifecycle.py` or `test_server.py` | 4 | Route-guard tests belong near the routing |
| `test_trn231_require_api_key.py` | `test_server.py` | 7 | Startup gate is a server concern |
| `test_trn235_config_repr_masking.py` | `test_config_from_env.py` | 5 | Config concern |
| `test_trn241_crew_id_env.py` | `test_lifecycle.py` | 3 | Container env injection |
| `test_trn_221_no_hardcoded_sel_path.py` | `test_hardening.py` | 1 | Static-analysis guard fits with hardening |
| `test_dashboard_default.py` | `test_caddy.py` | 6 | Dashboard config belongs with Caddy tests |
| `test_config_sync.py` | `test_config_from_env.py` | 1 | Same module |
| `test_auth_failure_reporting.py` | `test_auth.py` | 5 | Auth concern |
| `test_streaming_transfer.py` | `test_files.py` | 16 | Stream helpers belong in files tests |

The Admiral's instructions call for this consolidation. Section 6 below records what was actually merged.

---

## 6. Coupling issues (patch target audit)

All test files in the suite follow the "call-site principle": functions defined in `lifecycle.py` are patched as `lifecycle.X`, functions in `server.py` as `server.X`. A scan found no violations of this principle.

`test_trn225_memory_pressure.py` docstring explicitly states: *"each is patched as `server.X`"* — correct for those helpers.

`test_trn171_anthropic_endpoint_override.py` uses `patch.object(_server.cfg, ...)` — patches the live `cfg` object, which is the right approach for config-field overrides on a module-level singleton.

`test_trn222_ws_auth_invariants.py` uses `patch.object(server._dashboard_gate, "_sessions", ...)` — patches the gate's session store directly; correct.

**No coupling fixes needed.** All patch targets point at the correct module namespace.

---

## 7. Consolidation actions planned for TRN-244

The following merges will be performed (smallest/clearest wins first):

1. `test_config_sync.py` (1 test) → `test_config_from_env.py`
2. `test_auth_failure_reporting.py` (5 tests) → `test_auth.py`
3. `test_dashboard_default.py` (6 tests) → `test_caddy.py`
4. `test_trn_221_no_hardcoded_sel_path.py` (1 test) → `test_hardening.py`
5. `test_trn226_claude_setup_token_removed.py` (4 tests) → `test_server.py`
6. `test_trn231_require_api_key.py` (7 tests) → `test_server.py`
7. `test_trn235_config_repr_masking.py` (5 tests) → `test_config_from_env.py`
8. `test_trn241_crew_id_env.py` (3 tests) → `test_lifecycle.py`
9. `test_streaming_transfer.py` (16 tests) → `test_files.py`
10. `test_review_quick_fixes.py` (7 tests) → split: `TestNextUrl` → `test_caddy.py` (dashboard concern), `TestFiniteFloats` + `TestBackendListLineBreak` → `test_config_from_env.py`

TRN files with ≥9 tests that cover a coherent, self-contained regression story are **left in place** to preserve the regression-guard doc comment value:
- `test_trn156_lifecycle_memory_cron.py` (5 tests — kept; regression story is dense)
- `test_trn157_lifecycle_race_keypair.py` (9 tests — kept)
- `test_trn167_claude_backend.py` (20 tests — kept)
- `test_trn171_anthropic_endpoint_override.py` (10 tests — kept)
- `test_trn220_crew_api_headers.py` (4 tests — kept; tight invariant doc)
- `test_trn222_ws_auth_invariants.py` (7 tests — kept; tight invariant doc)
- `test_trn223_knowledge_autoingest.py` (4 tests, 2 skip — kept)
- `test_trn225_memory_pressure.py` (18 tests — kept; large enough standalone)
- `test_trn237_csp_nonce.py` (15 tests — kept)

After merges: ~10 files removed, test count unchanged.
