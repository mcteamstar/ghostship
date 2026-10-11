## MODIFIED Requirements

### Requirement: Config file format documentation
`docs/configuration.md` SHALL document the config file format (shell file exporting
variables), list all supported variables, and state the resolution order explicitly:
built-in default → config file → command-line flag, with no ambient-environment-variable
tier. It SHALL also state, for variables that are passed through into the transport
container's own runtime environment, that this is a distinct later step (`install.sh`
baking its own already-resolved values into `podman run -e` flags) and not something an
operator sets by exporting a variable in any shell.

The documentation SHALL also document the full model precedence chain:
`dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model field > `KC_MODEL_DEFAULT` >
KiroCrew built-in default

Variables removed from the operator-configurable surface (`HOST`, `GA_PORTAL_ADMIN_URL`,
`GA_FILE_TTL_SECS`, `GA_PICKUP_MAX_POLL_SECS`, `GA_MEMORY_WAIT_SECS`,
`KC_GATEWAY_TOKEN_TTL`, `GA_ENFORCE_HTTPS_REDIRECT`, `GA_CSP_ENFORCE`) SHALL NOT appear
in the supported variable list. `GA_PORTAL_PORT` SHALL appear only as a deprecated alias
with a note pointing to `PORT`.

The documentation SHALL include a "Knowledge auto-ingest" note stating that:
- ghostship does not enable knowledge auto-ingest;
- under KiroCrew 0.9.0+ (PR #2448) knowledge auto-ingest (artifact watcher, agent
  auto-add-documents path, folder ingestion) is opt-in rather than default-on;
- the disabled posture relies on the verified upstream default and is NOT pinned in the
  crew config, because verification against the pinned base image (`kiro_crew` 0.9.0rc4,
  `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`) found no single `knowledge.auto_ingest`
  boolean to pin — the real toggles (`knowledge.auto_ingest_artifacts`,
  `knowledge.auto_add_documents`) each already default to `false`;
- the open item (a future upstream default flip could silently enable ingest) is guarded by
  a CI regression test (`tests/unit/test_trn223_knowledge_autoingest.py`) rather than a
  config pin;
- an operator who wants knowledge built from commits in the mounted worktree must opt in
  explicitly.

#### Scenario: Config file section present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL contain a "Config file" section explaining that the file is a shell script exporting variables, listing all supported variable names, and stating the resolution order: built-in default → config file → command-line flag

#### Scenario: No ambient environment variable tier documented
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL NOT describe exporting a variable in the invoking shell as a supported way to configure `install.sh` or `uninstall.sh`

#### Scenario: Model precedence table present in docs
- **WHEN** reading `docs/configuration.md`
- **THEN** it SHALL include a model precedence table or section documenting: `dispatch(model=...)` > `KC_MODEL_OVERRIDE` > per-agent model > `KC_MODEL_DEFAULT` > KiroCrew built-in

#### Scenario: Removed vars absent from docs
- **WHEN** reading `docs/configuration.md`
- **THEN** the removed variables SHALL NOT appear as supported operator-configurable inputs

#### Scenario: Knowledge auto-ingest posture documented
- **WHEN** an operator reads the knowledge section of `docs/configuration.md`
- **THEN** they learn that auto-ingest is off by the verified upstream default, that it is
  deliberately NOT pinned (no `knowledge.auto_ingest` key exists to pin), that a CI test
  guards against an upstream default flip, and how to opt in explicitly if wanted
