# Capability migration

Paths are relative to the live OpenSpec specs directory. A whole-spec move retains all requirement owners within the named new path.

| Previous path | New path |
| --- | --- |
| `academy-backend-delivery` | `academy/backend-delivery` |
| `acp-prewarm` | `crew-lifecycle/startup` |
| `admiral-sig/payload-format` | `admiral-sig/payload-format` |
| `agent-backends` | `academy/agent-backends` |
| `agent-personas` | `academy/agent-personas` |
| `agent-skill-contracts` | `academy/agent-skills` |
| `auth/credential-profiles` | `auth/credential-profiles` |
| `captain/independent-review` | `captain/independent-review` |
| `captain/openspec-hygiene` | `captain/openspec-hygiene` |
| `captain-free-will-template` | `captain/free-will` |
| `claude-auth` | `auth/claude` |
| `codex-auth` | `auth/codex` |
| `config-file` | `configuration/file` |
| `crew-acp-backend` | `crew-lifecycle/backend` |
| `crew-governance` | `crew-lifecycle/governance` |
| `crew-image-build` | `installation/crew-images` |
| `crew-login` | `auth/crew-login` |
| `crew-manifest` | `academy/crew-manifest` |
| `crew-member-enrollment` | `crew-lifecycle/member-enrollment` |
| `crew-model` | `crew-lifecycle/configuration` |
| `crew-openspec-workflows` | `openspec-workflows/crew` |
| `crew-orchestration/dispatch-coordination` | `crew-orchestration/dispatch-coordination` |
| `crew-orchestration` | `crew-orchestration` |
| `crew-steering` | `academy/crew-steering` |
| `crew-types` | `academy/crew-types` |
| `crew-ui-spa-routing` | `transport/dashboard-routing` |
| `dashboard-session-auth` | `transport/dashboard-session-auth` |
| `dependency-management` | `installation/dependencies` |
| `ga-radar` | `transport/radar` |
| `installation/client-only` | `installation/client-only` |
| `installation/python-modules` | `installation/python-modules` |
| `installation` | `installation` |
| `installation/start-main` | `installation/start-main` |
| `installation/start-sh-shim` | `installation/start-sh-shim` |
| `kc090-memory-vector-similarity` | `crew-lifecycle/memory-retrieval` |
| `launch/profile-selection` | `auth/launch-profile-selection` |
| `mail/delivery-input-validation` | `mail/delivery-input-validation` |
| `mail` | `mail` |
| `mail-timestamps` | `mail/timestamps` |
| `mcp-server` | `mcp/server` |
| `mcp-server-config` | `mcp/configuration` |
| `persona-dispatch` | `task-orchestration/dispatch` |
| `proxy-hosting` | `transport/proxy-hosting` |
| `rate-limiting` | `transport/rate-limiting` |
| `registry/durability` | `registry/durability` |
| `secret-delivery-hardening` | `auth/secret-delivery` |
| `security-headers` | `transport/security-headers` |
| `shared-openspec-store` | `openspec-workflows/shared-store` |
| `task-timestamps` | `task-orchestration/timestamps` |
| `test-captain-helpers` | `testing/captain-helpers` |
| `test-orchestration` | `testing/orchestration` |
| `transport/auth-unit-tests` | `testing/auth-middleware` |
| `transport/caddy-proxy` | `transport/caddy-proxy` |
| `transport/captain-engine-tests` | `testing/captain` |
| `transport/crew-api-auth` | `transport/crew-api-auth` |
| `transport/crews-rest-api` | `transport/crews-rest-api` |
| `transport/dashboard-auth` | `transport/dashboard-auth` |
| `transport/dashboard-login` | `transport/dashboard-login` |
| `transport/dashboard-login-csrf` | `transport/dashboard-login-csrf` |
| `transport/dashboard-proxy` | `transport/dashboard-proxy` |
| `transport/exception-handling-policy` | `transport/exception-handling-policy` |
| `transport/fleet-overview` | `transport/fleet-overview` |
| `transport/internal-fleet-api` | `transport/internal-fleet-api` |
| `transport/network-split` | `transport/network-split` |
| `transport/security-primitives-tests` | `testing/security-primitives` |
| `transport/tls` | `transport/tls` |
| `transport-bind-guard` | `transport/bind-guard` |
| `transport-test-lifecycle` | `testing/launcher` |
| `trn-captain-mail` | `captain/mail` |
| `trn-cli` | `cli` |
| `trn-openapi-schema` | `transport/openapi` |
| `trn-openspec-validation` | `openspec-workflows/validation` |
| `trn-worker-evac` | `file-transfer/evac` |
| `yaml-config` | `configuration/yaml` |

## Split capabilities

### `crew-lifecycle`

| Destination | Requirements transferred |
| --- | --- |
| `crew-lifecycle/provisioning` | Crew creation via launch · Crew teardown via nuke · Nuke dry-run reports scheduled jobs · Confirmed nuke clears scheduled jobs before container teardown · Crew setup completion is all-or-nothing · Admiral signing key is ready before crew setup · Setup failures prevent crew registration · Setup steps follow dependency order · Crew and resource naming convention · Documentation frames crews as persistent workspaces · Crew container environment includes KIROCREW_CREW_ID |
| `transport/dashboard-provisioning` | REST API to retrofit or remove a dashboard |
| `crew-lifecycle/startup` | Waiter timeout is sufficient for worst-case leader restart · Concurrent restart outcome reads are generation-stable · Crew auto-start serialised per crew · _ensure_crew_running checks registry entry after container_start · ensure_running leader election is single-lock |
| `crew-lifecycle/configuration` | Headless crew config overrides · Crew configuration supports operator-tunable task timeout · dangerously_skip_permissions usage is annotated · Configurable model default patch · Crew config patches sandbox=off for Podman rootless compatibility · subagent_max_turns ceiling documentation |
| `transport/crew-gateway` | Bounded gateway session-token lifetime · CSRF/cookie auto-recovery on stale credentials · Gateway liveness probe · Retry with backoff on transient failures · User-facing error messages on recovery failure · /continue path detection uses endswith, not substring match · Gateway error detail reaches the caller · Cookie refresh is atomic under the registry lock |
| `transport/fleet-overview` | Gateway health field in crews() output · crews() includes crew image version · Crew list response includes timing metadata · crews() active_crews reflects actual Podman state |
| `auth/backend-login` | Concurrent login guard is atomic |
| `auth/crew-credentials` | Authentication gate precedes registry write in launch |
| `crew-lifecycle/capacity` | Pre-launch memory gate · Configurable spawn_min_memory_gb patch · Configurable resource pressure thresholds · Active crew limit enforced before restart |
| `registry/reconciliation` | Config patch applied on reconcile restart · Registry reconciliation is idempotent · Reconcile registry deletion is timestamp-guarded |
| `registry/durability` | Registry file written with restricted permissions |
| `admiral-sig/key-delivery` | Threat model for admiral secret delivery is documented |
| `installation/crew-images` | Base image version |
| `task-orchestration/timestamps` | Bounded in-process memory for task timestamp tracking |
| `crew-lifecycle/idle-and-wake` | Idle monitor releases registry lock before container_stop · Idle stop and crew wake are serialized |
| `task-orchestration/dispatch` | slot=True falls back with a warning in dispatch |

### `idle-and-recovery`

| Destination | Requirements transferred |
| --- | --- |
| `crew-lifecycle/idle-and-wake` | Idle container stop · Enabled schedules keep a crew alive · Unknown activity state fails safe · Stopped crews restart on the next request · Due work wakes stopped crews after startup · Survives podman-machine / host restarts |
| `crew-lifecycle/startup` | Restart applies required configuration before final gateway wait · Concurrent restart callers share a stable outcome · _ensure_crew_running waiter propagates leader failure |
| `task-orchestration/scheduling` | Gateway cron state is reconciled after restart · Schedule monitor uses gateway enabled state · Schedule monitor falls back to registry when gateway is unreachable |
| `registry/reconciliation` | Registry reconciliation on startup · Eager registry self-healing for externally stopped containers |

### `task-orchestration`

| Destination | Requirements transferred |
| --- | --- |
| `task-orchestration/dispatch` | Task dispatch and member-slot routing · Legacy slot values do not create legacy sessions · Persona allowlist for task submission · Dispatch tool supports per-task model override · dispatch accepts tasks list as an alternative overload |
| `task-orchestration/pickup` | Task status and collection · Blocking wait on a single task · pickup accepts task_ids list for batch collection |
| `task-orchestration/steer` | Steering running or completed tasks |
| `task-orchestration/scheduling` | Recurring task scheduling · Schedule tool supports cancel action · Schedule tool supports list action · Dispatch tool supports delay parameter · transport://jobs resource exposes scheduled jobs · Transport maintains authoritative schedule registry · Transport wakes idle crews before scheduled ticks fire · _reconcile_registry re-seeds gateway schedule on restart · schedule tool supports delay parameter · Idempotent one-shot job deletion · Schedule registry cleared on confirmed nuke · Schedule tool supports per-job model override |
| `captain` | Captain standing-orders check-in · Captain standing-orders check-in supports model override |
| `transport/fleet-overview` | Crew listing |

### `captain`

| Destination | Requirements transferred |
| --- | --- |
| `captain/templates` | captain tool description lists free-will as a built-in template · User orders directory adds templates · User templates override matching built-ins · Missing user orders directory preserves defaults · Order templates preserve retry state after memory refusal · Order templates escalate sustained memory refusals |
| `captain` | Raven self-cancels through the transport · Transport stop endpoint disables the Captain schedule · captain stop always disables the schedule registry entry · Captain dispatch uses a compatible model on Claude-backend crews · Captain check-in defers under critical memory pressure · Captain check-in fails open when memory probing is unavailable · Captain schedule tracks consecutive pressure failures · Captain escalates once after sustained pressure · Cron captain schedule evaluates first fire from cron expression · _steer_captain_checkin classifies errors by HTTP status code · Captain paces multiple task starts in a check-in · Captain recovers from a confirmed Raven session restore failure |
| `transport/dashboard-auth` | verify_password handles scrypt resource exceptions |

### `autonomous-orchestration`

| Destination | Requirements transferred |
| --- | --- |
| `captain` | One Captain check-in per crew · Captain exposes an explicit action contract · Captain status surfaces both mail directions · Captain orders are stored as mail · Ordering ensures a recurring Raven check-in · Raven evaluates orders on each check-in · Raven prevents duplicate persona dispatch · Persona mailboxes provide supplemental crew context · Raven uses the CLI and gateway API for distinct operations · Captain monitor starts a fresh check-in after completion · Raven prompts use ghostship-spawn for gateway work · Raven task briefs respect the crew tool gate · Raven treats tool refusals as crew gate blocks · Change artifacts are not Raven's instructions |
| `captain/templates` | Standing orders can be composed from a named template · Captain order templates are filesystem-backed · Template placeholder contract · transport://orders resource lists templates dynamically |
| `captain/spec-driven-development` | The built-in SDD template preserves the OpenSpec lifecycle discipline |
| `transport/crew-gateway` | Continue failures do not trigger stale-cookie recovery |

### `crew-auth`

| Destination | Requirements transferred |
| --- | --- |
| `auth/backend-login` | First-time device auth flow · Kiro auth state transitions · Kiro login method selects the identity provider |
| `auth/crew-credentials` | Kiro auth reused across crews · Crew secrets not persisted in plaintext after injection |
| `admiral-sig/key-delivery` | Admiral signing keys are isolated · Admiral mail is signed with Ed25519 · Admiral signature verifier uses the public key only |

### `backend-credentials`

| Destination | Requirements transferred |
| --- | --- |
| `auth/backend-credentials` | Backend credentials persisted under DATA_DIR · One active credential per backend · Supported credential methods per backend · Interactive credential flows store into the same slot · Credential status reported per backend · Logout removes stored backend credentials · Logout is idempotent when no credential is stored |
| `auth/backend-login` | Login routes are per backend and per method · Pasted credentials stored through their login route · Login requires the backend to be enabled · Bare login and logout paths are unassigned · Logout cancels pending login flows · Launch starts the backend's interactive login when no credential is stored |
| `auth/crew-credentials` | Logout leaves running crews unchanged · Credentials resolved at each crew launch · Credential delivered to crews according to its method |

### `file-transfer`

| Destination | Requirements transferred |
| --- | --- |
| `file-transfer/evac` | Extracting files and diffs via evac · Non-empty path required for evac |
| `file-transfer/supply` | Supplying files and archives via supply · Safe archive extraction · Crew uploads enforce resource budgets |
| `file-transfer/security` | Presigned URL expiry and integrity · crew_id format validated in file handler routes |

### `file-transfer-security`

| Destination | Requirements transferred |
| --- | --- |
| `file-transfer/security` | Full-length HMAC · Operation-typed tokens · Path canonicalisation · `ref` validation · Token expiry · Valid presigned tokens bypass global Bearer auth at all layers · Upload and download presigned bypass is symmetric · Presigned URL issuance is audited · Token verification outcome is audited · Upload mutations stay within the crew workspace |
| `transport/crew-gateway` | Gateway error response body is redacted before surfacing to callers |
| `testing/file-transfer` | HMAC sign/verify machinery has direct unit tests |

### `transport-test-coverage`

| Destination | Requirements transferred |
| --- | --- |
| `testing/monitors` | _cron_activity_since helper test coverage · _cron_has_enabled_job helper test coverage · _note_idle_skip helper test coverage · _schedule_monitor test coverage · _idle_monitor test coverage · _idle_monitor handles 401 with cookie refresh · _captain_monitor test coverage |
| `testing/registry` | _reconcile_registry test coverage · _reconcile_registry handles stale snapshot · Crew registry key compatibility has test coverage |
| `testing/launcher` | _finish_crew_setup ordering test · _reseed_crew_schedules captain branch test coverage · lifecycle.py unit test module exists · Launch alias resolution has test coverage · Crew persistence and MCP payload compatibility have test coverage |
| `testing/login` | Login flow edge case tests · _handle_login_get clears guard correctly under concurrency · Claude login lifecycle test coverage |
| `testing/workflow` | Test suite runs safely inside crew containers · e2e suite fixture model · pytest-cov is run in CI · Critical transport modules have direct unit test coverage · Python integration suites run through the supported test workflow |
| `testing/crew-gateway` | _crew_api_with_recovery test coverage |
| `testing/server` | _ssl_context_factory test coverage · TransportSecretMiddleware and _load_transport_secret test coverage · server.py pure utility function test coverage · Health endpoint unit test coverage · REST crew payload compatibility has test coverage |
| `testing/file-transfer` | Streaming transfer classes have test coverage |
| `testing/installation` | Static guardrail test prevents hardcoded pre-0.9.0 SEL path · Installation and startup have an automated end-to-end smoke path |
| `testing/captain` | _append_captain_mail I/O path test coverage · _captain_do_order/status/stop branch test coverage · captain_engine.py dispatch and steer paths have unit tests |
| `testing/dashboard` | _handle_crew_ui_ws_proxy test coverage · CaddyPortal port pool allocation · Module-level port wrappers delegate to default portal · CaddyPortal.register_crew builds correct reverse-proxy config · CaddyPortal.deregister_crew calls Caddy admin DELETE · Module-level thin wrappers delegate to default portal · _caddy_admin_url returns correct constant · CaddyPortal constructor stores fields correctly |
| `testing/podman` | container_exec_stdin unit test coverage · PodmanClient has dedicated unit tests |
| `testing/mcp` | tools.py MCP API surface has dedicated unit tests · Comp discovery resource aliases have test coverage |
| `testing/academy` | academy.py comp registry has error-path tests |
| `testing/admiral-signature` | Admiral signature verifier has direct behavioral coverage |

### `batch-dispatch`

| Destination | Requirements transferred |
| --- | --- |
| `task-orchestration/dispatch` | Batch dispatch accepts bounded task lists · Batch dispatch returns per-task results · Batch registry record tracks member status · Gateway refusal preserves accepted batch members |
| `task-orchestration/pickup` | Blocking batch pickup returns per-task results · Batch lookup matches task ID subsets · Lost-member detection |

## Consolidation after the ownership move

The tables above record the original requirement moves. The following changes supersede entries for consolidated requirements.

| Area | Canonical owner and decision |
| --- | --- |
| Delayed tasks | `task-orchestration/scheduling` retains one-shot `schedule(delay=...)`. The superseded `dispatch(delay=...)` requirement and its two scenarios were removed. |
| Gateway diagnostics and recovery | `transport/crew-gateway` owns actionable diagnostics, final HTTP status, redaction and the 500-character detail limit. The generic HTTP 400 stale-cookie rule and redundant MCP error requirement were retired. Structured credential refusal and uncertain write handling remain explicit. |
| Raven recovery | `captain` combines the older fresh-check-in and continuation classification rules. Confirmed missing or failed sessions permit replacement, busy preserves the current ID, and unknown acceptance holds when correlation is unavailable. The late restore-failure requirement remains separate. |
| Dispatch and pickup | `task-orchestration/dispatch` combines batch input and enrollment-based slot requirements. `task-orchestration/pickup` combines batch polling and replaces the duplicate mail contract in `mail` and `captain/mail`, matching actual task and crew-wide fields. Lost-member reporting and the Captain status mailbox contract remain distinct. |
| Startup election | `crew-lifecycle/startup` combines six overlapping requirements under one generation-stable leader and waiter contract. It retains timeout, leader failure, healthy follow-up, cross-crew admission, and generation-change coverage. Provisional start and configuration bounce and removal during restart retain their own requirements. |
| Credential scope | `auth/backend-credentials` describes credential replacement, interactive authentication, status and logout by backend and profile. `auth/credential-profiles` owns profile names, default targeting and legacy migration. |

### Dashboard, configuration and Captain tests

- Dashboard login owns the actual per-page `gs_csrf` cookie and form-field comparison. The obsolete process-wide token spec and header-based login scenarios were retired. Dashboard session auth owns issuance, cookie flags and redirect validation. Dashboard routing owns port allocation and forwarding. The proxy capabilities targeted by TRN-328 retain their paths and content.
- `configuration/yaml` owns resolution precedence and automatic legacy migration. Installer-specific outcomes remain as scenarios there. The obsolete shell-source comment requirement was retired because install uses the YAML resolver.
- `testing/captain` owns Captain engine behavior coverage in one requirement. It replaces the obsolete interrupt fallback expectation with the current rejection, busy, confirmed recovery, and uncertain-acceptance paths. Mail I/O and helper coverage remain distinct.

## Active changes and references

- TRN-328's active deltas still target `transport/caddy-proxy` and `transport/dashboard-proxy`. Both paths and their existing requirement blocks are preserved.
- The remaining open changes declare no spec deltas. The maintained OpenSpec skills already resolve full capability paths. The archives retain their historical spec paths.

### Updated live references

- Task dispatch and pickup now reference the applicable batch requirements within their own specs.
- Academy personas and steering now reference `academy/crew-manifest`.
- Transport proxy hosting now references `transport/dashboard-routing`.
- MCP's purpose now points to the lifecycle, task and transfer capability groups.

## Verification

- OpenSpec 2.0.0 strict validation passed for 104 live specs and seven active changes.
- Before consolidation, all 733 baseline requirement blocks and 2,185 scenarios matched after normalising documented reference updates. The final live tree has 700 requirements and 2,149 scenarios after combining duplicates and removing superseded behavior as listed above.
- A disposable change synced into `transport/crew-gateway` and archived with its nested delta path intact.
- All 102 Captain, Raven prompt, and OpenSpec asset contract tests passed.

- The 271 focused task, Captain, gateway, credential-route, lifecycle, and MCP tool unit tests passed after consolidation.
- The dashboard, WebSocket, Captain engine, configuration, YAML and installer unit tests passed with 339 passed and one skipped.
