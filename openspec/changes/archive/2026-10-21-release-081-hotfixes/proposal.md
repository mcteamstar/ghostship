# Proposal

## Why

Testing TRN-262, TRN-263 and TRN-264 on live crews turned up a handful of small defects. None needs its own change, but together they cost real debugging time on 2026-10-20:

- A crew gateway's 400 reason never reaches the caller. When every dispatch on a claude crew failed with `Agent 'ghost' not found`, MCP `dispatch` reported only "crew … is unresponsive", and the reason sat in the crew's own log.
- Raven on a kiro crew applied the specs of the change it was building to itself, and held on a rule ("hold if `ghostship-spawn` is missing") that only takes effect after that change lands.
- Running the unit tests leaves `__pycache__/` inside `academy/skills/ghostship-spawn/scripts/`, and whole-directory skill delivery copies it into every crew.
- `ghostship status` always prints "ga-portal-data volume not found" because Compose names the volume `ga_ga-portal-data`. The `transport/tls` spec already requires status to show the CA path, so this is a bug against an existing requirement.
- e2e: the kiro-auth test's skip reason still says logout clears every crew's identity, which stopped being true in TRN-258, and the Podman socket default is a Linux path, so the restart test never runs on macOS.
- `openspec/changes/trn-265-openspec-1140-upgrade/` was left behind after TRN-265 was archived, so `openspec list` still shows it as active.

Where each defect comes from:

| Fix | Introduced or exposed by |
|---|---|
| Gateway error detail | TRN-2 (transport self-healing), with TRN-230/238; hit while testing TRN-264 |
| Change artifacts vs Raven's instructions | TRN-263; seen when a kiro crew drove TRN-263 |
| Bytecode caches in skills | TRN-263 (whole-directory skill copy), kept by TRN-264's staging |
| Portal volume lookup | TRN-103 (portal mandatory) and TRN-92; the `ga_` prefix comes from TRN-59's Compose project name |
| e2e kiro-auth skip reason | TRN-258 (logout no longer touches running crews) |
| e2e Podman socket default | Linux-only since the e2e suite was added; last touched in TRN-213 |
| Leftover TRN-265 folder | TRN-265 archive step |

## What Changes

- Crew API errors carry the gateway's response: when a request to a crew gateway finally fails with an HTTP error, the error returned to the MCP caller includes the HTTP status and the gateway's response body (truncated, with credentials redacted) instead of only "unresponsive".
- Order templates (`spec-driven-development`, `independent-review`) tell Raven that a change's specs and design describe the target behaviour after that change is implemented, not its own current instructions.
- Skill staging skips `__pycache__/` directories and `*.pyc` files.
- `ghostship status` and the install output find the portal data volume under its Compose name (`ga_ga-portal-data`), falling back to the bare name.
- e2e fixes: correct the kiro-auth skip reason; default `GHOSTSHIP_PODMAN_SOCKET` to the macOS dedicated-machine socket when running on macOS.
- Remove the leftover `openspec/changes/trn-265-openspec-1140-upgrade/`.
- **Out of scope (deliberately):**
  - Whether a 400 should trigger cookie refresh and container restart. The `crew-lifecycle` spec mandates it, and changing it needs a separate change once the original 400 case is understood.
  - Pinning `AGENTS_REF` to a SHA (left on `main` pending a decision).
  - Making the CA certificate usable on macOS. The volume mountpoint `ghostship status` prints is a path inside the Podman VM, so on a Mac it isn't on the host filesystem. This change only fixes the lookup, which satisfies `transport/tls`; a host-usable path is a follow-up.
  - The `token_signing.key` sandbox failure, zombie Raven cycles, Captain status nulls, and the stray `ghostship auth` call during install. These are to be investigated first.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `crew-lifecycle`: adds a requirement that a crew gateway's HTTP error detail reaches the caller once recovery gives up.
- `autonomous-orchestration`: adds a requirement that order templates distinguish a change's target behaviour from Raven's current instructions.
- `crew-manifest`: "Selected skills are delivered whole" excludes Python bytecode caches.

## Impact

- **Code:** `transport/lifecycle.py` (final error message in `_crew_api_with_recovery`), `transport/academy.py` (`_stage_skills` filter), `ghostship` CLI and `bin/install.sh` (volume lookup).
- **Academy:** `academy/orders/spec-driven-development.md`, `academy/orders/independent-review.md`.
- **Tests:** unit tests for the error detail, the skill filter, the template sentence and the volume lookup; e2e helper and skip text.
- **Repo:** delete `openspec/changes/trn-265-openspec-1140-upgrade/`.
- **Operators:** `ghostship upgrade`; relaunch crews to pick up the template and skill changes.
