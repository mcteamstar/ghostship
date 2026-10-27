# Tasks: TRN-274 — Docs Refresh

- [ ] H-10: Update `docs/architecture.md` lines 9/11 and `docs/configuration.md` line 58 to reference KC 0.10.0 / new index digest
- [ ] H-11: Add `## v0.9.0` section to `CHANGELOG.md` covering TRN-271 (base image bump to KC 0.10.0, multi-arch index digest, ghostship version 0.9.0)
- [ ] H-12: Fix `docs/portal.md` — correct "1024 ports" to "64 ports"; update firewall example to `64058:65121/tcp`
- [ ] M-9: Fix `CREW_GATEWAY_PORT` file attribution (`transport/constants.py`, not `server.py`)
- [ ] M-10: Fix `KIRO_API_KEY` description — moved to credential store in TRN-233, not removed
- [ ] M-11: Remove pending TRN-16 annotation from `docs/troubleshooting.md`
- [ ] M-12: Update `docs/release-notes-0.6.0.md` Upgrading section to current config names (`ghostship.yaml`, not `ghostship.conf`/`GA_AGENT_BACKENDS`)
- [ ] L-6: Add `GA_DASHBOARD_PORT_RANGE_SIZE` to `docs/portal.md` config table
- [ ] L-7: Remove duplicate `PODMAN_SOCKET` entry from config tables in `docs/configuration.md`
- [ ] L-8: Update `GA_REQUIRE_API_KEY` entry to "removed" (not deprecated)
- [ ] I-8: Add `transport/constants.py` and `container_scripts/` to project layout tree in `docs/architecture.md`
- [ ] I-9: Document `images.agents_ref` in `docs/configuration.md`
- [ ] I-11: Review TRN-267 (`indy-081-doc-fixes`) pylon; close or update items superseded by TRN-271/TRN-274
