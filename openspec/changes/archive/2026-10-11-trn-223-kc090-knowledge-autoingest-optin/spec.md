# Delta Spec — TRN-223 Knowledge auto-ingest opt-in

This delta describes the behaviour of ghostship's crew config patching with respect to
KiroCrew 0.9.0's opt-in knowledge auto-ingest (PR #2448). The functional behaviour of the
running crew is **unchanged**; the delta formalises the "off by default" posture and the
documentation.

## MODIFIED Requirements

### Requirement: Crew config overrides do not enable knowledge auto-ingest

The config overrides written by `_patch_crew_config()` into each crew's
`config.local.json` SHALL NOT enable any knowledge auto-ingest path (file-watcher, git
commit hook, or clipboard capture). The resulting crew SHALL run with knowledge
auto-ingest disabled, matching KiroCrew 0.9.0's new default.

Under KiroCrew ≤ 0.8.x the auto-ingest paths were default-on but were never triggered in a
headless crew container (no clipboard; the working tree is a transient worktree, not a
registered watched folder). Under KiroCrew 0.9.0+ they are default-off. In both cases the
crew's effective behaviour is "no auto-ingest", so no runtime behaviour changes.

#### Scenario: Fresh crew start under KiroCrew 0.9.0 does not auto-ingest
- **WHEN** a spec-ops crew container starts on a KiroCrew 0.9.0+ base image
- **THEN** no knowledge auto-ingest path is active
- **AND** no knowledge entries are created from the mounted worktree, commits, or clipboard

#### Scenario: Upgrade from 0.8.x to 0.9.0 is a no-op for ingest
- **WHEN** an existing crew's base image is bumped from `0.8.0` to `0.9.0-insider.4`
- **THEN** the crew's auto-ingest behaviour is identical before and after (disabled)

### Requirement: Config patcher deep-merges a knowledge section when present

`transport/container_scripts/patch_crew_config.py::patch_config()` SHALL deep-merge any
top-level `knowledge` section passed in `full_overrides` into `config.local.json`, using
the existing `_deep_merge()` behaviour (recurse into dict values, overwrite scalars). No
change to the patcher is required to support a `knowledge` section — this requirement
records that the existing generic deep-merge already covers it.

#### Scenario: knowledge override is written to config.local.json
- **WHEN** `full_overrides` includes `{"knowledge": {"auto_ingest_artifacts": true}}`
- **THEN** `config.local.json` contains a top-level `knowledge` object with
  `auto_ingest_artifacts: true` after patching
- **AND** existing top-level sections (`agent`, `session`, `telemetry`, `agents`, …) are
  preserved

## ADDED Requirements

### Requirement: Explicit disabled posture is tracked via CI (D1 = Option B)

D1 resolved to **Option B** — no config pin. Verification against the pinned base image
(`kiro_crew` 0.9.0rc4, `ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4`) established that the
assumed key `knowledge.auto_ingest` does **not exist**. The real ingest toggles are
`knowledge.auto_ingest_artifacts` and `knowledge.auto_add_documents`, each defaulting to
`false`. Pinning the non-existent key would be an inert dead key, so no key is written.
The disabled posture relies on the verified upstream default, guarded by a CI regression
test rather than a config pin. `full_overrides` SHALL NOT contain a `knowledge` section.

#### Scenario: Upstream default flip is caught by the regression test
- **GIVEN** the disabled posture relies on the verified upstream default (D1 = Option B)
- **WHEN** a future KiroCrew version changes a knowledge ingest toggle's built-in default
  to `true` (i.e. `auto_ingest_artifacts` or `auto_add_documents`)
- **THEN** `tests/unit/test_trn223_knowledge_autoingest.py` fails in CI, surfacing the
  change for an explicit re-decision
- **AND** no ingest is silently enabled inside crew containers without notice

### Requirement: Documentation records the opt-in posture

`docs/configuration.md` SHALL contain a note stating that ghostship does not enable
knowledge auto-ingest, that under KiroCrew 0.9.0+ it is opt-in, and that an operator who
wants knowledge built from commits in the mounted worktree must opt in explicitly.

#### Scenario: Operator reads the knowledge note
- **WHEN** an operator reads the knowledge section of `docs/configuration.md`
- **THEN** they learn auto-ingest is off by default and how/why it stays off

## Configuration surface after this change

No new config keys are written by ghostship. The disabled posture relies on the verified
upstream defaults:

| Config key | Scope | Default value | Source |
|---|---|---|---|
| `knowledge.auto_ingest_artifacts` | `config.local.json` (via upstream default) | `false` | KiroCrew 0.9.0 `KnowledgeConfig` (opt-in) |
| `knowledge.auto_add_documents` | `config.local.json` (via upstream default) | `false` | KiroCrew 0.9.0 `KnowledgeConfig` (opt-in) |

No new ghostship `GA_*` operator env vars are introduced. Neither key is written by
ghostship — they are upstream defaults recorded here as the grounding for D1 = Option B.
