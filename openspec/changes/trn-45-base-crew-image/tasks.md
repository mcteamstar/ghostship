## Tasks

- [ ] Create `crews/_base/` directory
- [ ] Write `crews/_base/Containerfile`: `FROM ghcr.io/kirodotdev/kirocrew:0.3.0`, copy in mailutils/msmtp install block, Maildir provisioning, `msmtprc`/`maildeliver`/`sendmail-local`/`verify-admiral-sig` COPYs, `seed_kiro_db.py` pre-seed block — move all of these verbatim from `crews/spec-ops/Containerfile`; remove `ARG VERSION`/`LABEL` (those stay in spec-ops); move kiro-cli fragility warning comment here
- [ ] Move `crews/spec-ops/maildeliver` → `crews/_base/maildeliver`
- [ ] Move `crews/spec-ops/sendmail-local` → `crews/_base/sendmail-local`
- [ ] Move `crews/spec-ops/verify-admiral-sig` → `crews/_base/verify-admiral-sig`
- [ ] Move `crews/spec-ops/msmtprc` → `crews/_base/msmtprc`
- [ ] Move `crews/spec-ops/seed_kiro_db.py` → `crews/_base/seed_kiro_db.py`
- [ ] Rewrite `crews/spec-ops/Containerfile`: `FROM localhost/base:latest`, then Node.js install block (keep `NODESOURCE_SETUP_SHA256` here), then OpenSpec CLI install, then `ARG VERSION` + `LABEL org.ghostship.version=$VERSION`
- [ ] Update `install.sh`: add `podman build -t localhost/base:latest --build-arg VERSION="${VERSION}" "${GHOSTSHIP_DIR}/crews/_base"` before the existing spec-ops build step; update the spec-ops build to pass `--build-arg VERSION="${VERSION}-spec-ops"` so the OCI label reads e.g. `0.1.0-spec-ops`
- [ ] Verify `crews/registry.json` does not reference `_base` (it shouldn't — no change needed, just confirm)
- [ ] Run `install.sh` locally (or on Academy) to confirm both images build and `launch` still works end-to-end
