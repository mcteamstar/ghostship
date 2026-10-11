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
- **WHEN** `full_overrides` includes `{"knowledge": {"auto_ingest": false}}`
- **THEN** `config.local.json` contains a top-level `knowledge` object with
  `auto_ingest: false` after patching
- **AND** existing top-level sections (`agent`, `session`, `telemetry`, `agents`, …) are
  preserved

## ADDED Requirements

### Requirement: Explicit disabled posture is pinned (if D1 accepted)

If decision D1 (design.md) is accepted, the `full_overrides` dict in `_patch_crew_config()`
SHALL include an explicit `"knowledge": {"auto_ingest": false}` entry so the disabled
posture is pinned into `config.local.json` and survives (a) KiroCrew gateway upgrades, and
(b) any future upstream change to the default value of `knowledge.auto_ingest`.

If D1 is rejected (track upstream default instead), this requirement is dropped and the
posture relies on KiroCrew 0.9.0's own default-off behaviour.

#### Scenario: Upstream default flip cannot silently enable ingest
- **GIVEN** D1 is accepted and `knowledge.auto_ingest=false` is pinned in `full_overrides`
- **WHEN** a future KiroCrew version changes its built-in default for `knowledge.auto_ingest` back to `true`
- **THEN** the crew still runs with auto-ingest disabled, because `config.local.json` is
  deep-merged over `config.json` and pins the value

### Requirement: Documentation records the opt-in posture

`docs/configuration.md` SHALL contain a note stating that ghostship does not enable
knowledge auto-ingest, that under KiroCrew 0.9.0+ it is opt-in, and that an operator who
wants knowledge built from commits in the mounted worktree must opt in explicitly.

#### Scenario: Operator reads the knowledge note
- **WHEN** an operator reads the knowledge section of `docs/configuration.md`
- **THEN** they learn auto-ingest is off by default and how/why it stays off

## Configuration surface after this change

| Config key | Scope | Value | Introduced by |
|---|---|---|---|
| `knowledge.auto_ingest` | `config.local.json` (crew) | `false` (pinned, if D1 accepted; otherwise relies on upstream default) | KiroCrew 0.9.0 (PR #2448) |

No new ghostship `GA_*` operator env vars are introduced. The key, if written, is a fixed
headless-crew override alongside `stt.enabled=false` and `telemetry.beacon_enabled=false`
in `_patch_crew_config()` — not operator-configurable.
