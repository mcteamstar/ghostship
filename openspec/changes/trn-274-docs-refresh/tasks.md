# Tasks: TRN-274 — Docs Refresh

- [x] H-10: Update `docs/architecture.md` lines 9/11 to `kirocrew:0.10.0`; update `docs/configuration.md` line 58 SHA to `b6d0b9a3...` and description
- [x] H-11: Add `## v0.9.0` section to `CHANGELOG.md` (KC 0.10.0 base image, multi-arch index digest, ghostship version bump, gateway timeout)
- [x] H-12: Fix `docs/portal.md` line 206 — "1024 ports" → "64 ports (default)"; update firewall example to `64058:64121/tcp`
- [x] M-9: Fix `docs/configuration.md:102` — change `CREW_GATEWAY_PORT` file attribution from `server.py` to `transport/constants.py:21`
- [x] M-10: Update `KIRO_API_KEY` description — "moved to credential store via `ghostship auth login kiro --method api-key`" (not removed)
- [x] M-11: Remove pending TRN-16 annotation from `docs/troubleshooting.md`
- [x] M-12: Update `docs/release-notes-0.6.0.md` Upgrading section — replace `ghostship.conf`/`GA_AGENT_BACKENDS` with current `ghostship.yaml` config equivalents
- [x] L-6: Add `GA_DASHBOARD_PORT_RANGE_SIZE` row to `docs/portal.md` configuration table
- [x] L-7: Remove duplicate `PODMAN_SOCKET` entry from `docs/configuration.md`; keep the more complete entry
- [x] L-8: Remove or mark `GA_REQUIRE_API_KEY` as fully removed in `docs/configuration.md`
- [x] I-8: Add `transport/constants.py` and `container_scripts/` to the project layout tree in `docs/architecture.md`
- [x] I-9: Document `images.agents_ref` in `docs/configuration.md`
- [x] I-11: Review TRN-267 pylon; close items superseded by TRN-274; update remainder
