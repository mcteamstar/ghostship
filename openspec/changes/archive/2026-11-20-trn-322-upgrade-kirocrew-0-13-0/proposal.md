# Proposal

## Why

Ghostship pins its crews to KiroCrew v0.12.2. KiroCrew v0.13.0 stable was published on 2026-11-19 and is the target for Ghostship 0.13.0. It also fixes the IAM Identity Center profile lookup that Ghostship's kiro login depends on: profiles listed past the first page and profiles served from a control plane other than the Identity Center region. The earlier `0.13.0-rc.3` discovery informed the integration plan; the stable image, its digest, bundled Kiro CLI version, and SQLite schema must now be verified directly before changing the pin.

The 2026-11-17 KiroCrew v0.13 discovery, run by the `kc-discovery-claude` crew against `v0.13.0-rc.3`, found one integration change that affects Ghostship directly. In v0.13, `POST /api/spawn` with no `backend` inherits a backend from the parent session when that session was created with a harness pick. Ghostship's dispatch and Captain bodies name no backend, so after the upgrade the runtime of a dispatched task would depend on gateway-side session state rather than on the crew's recorded backend.

## What Changes

- Advance the immutable `KC_BASE_IMAGE` pin to the verified KiroCrew `0.13.0` stable multi-architecture index digest in the admission build default and the matching `transport/config.py` default. The transport also uses this image for ephemeral login containers, so the pin moves the login's kiro-cli too.
- Inspect the pinned image for its actual Kiro CLI version and its kiro-cli SQLite migration rows and table schema. Update `seed_kiro_db.py` if they differ from the v0.12.2 seed (11 rows, versions 0 to 10), and record the evidence.
- Name the crew's backend on every transport-originated `POST /api/spawn` (single dispatch, batch dispatch, Captain check-in, scheduled immediate dispatch, and scheduled tick dispatch), mapped from the crew's recorded `acp_backend` to KiroCrew's request spelling (`kiro`, `claude`, `codex`). The in-crew `ghostship-spawn` helper is unchanged; its nested spawns inheriting their parent's harness is the intended behaviour.
- Review the KiroCrew 0.13.0 changelog and the discovery report for other integration effects, and record findings and no-impact conclusions on the TRN-322 Plane ticket.
- Refresh dependency inventory, operator documentation and the changelog for the new pin.
- Build the images and smoke-test fresh kiro and claude crews: gateway readiness, kiro Identity Center login with profile capture, auth injection, enrolment, dispatch, Captain check-in, and the `kiro_signin` check.

Out of scope, and a separate change: making dispatched work visible in the dashboard (the discovery's watch-chat option and the proposed upstream owner-tier work-dispatch route).

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-image-build`: the required KiroCrew image becomes the verified stable `0.13.0` multi-architecture digest, and the kiro-cli DB seed must be re-verified against that image.
- `crew-acp-backend`: transport-originated spawns must name the crew's recorded backend, so a task's runtime cannot change through gateway-side backend inheritance.

## Impact

- `crews/_base/admission/Containerfile`, `transport/config.py`: image pin and version annotations.
- `crews/_base/graduation/seed_kiro_db.py`, `crews/_base/graduation/Containerfile`: seed verification annotation, and seed logic only if the schema differs.
- `transport/tools.py` (single dispatch body), `transport/lifecycle.py` (`_dispatch_batch` body), `transport/captain_engine.py` (Raven check-in body): a `backend` field on `/api/spawn`.
- `openspec/specs/crew-image-build/spec.md`, `openspec/specs/crew-acp-backend/spec.md`: requirement deltas.
- `dependencies.yaml`, `docs/configuration.md`, `docs/architecture.md`, `CHANGELOG.md`.
- Rebuilt transport, login and crew images. Existing crews keep their current image until they are recreated.
