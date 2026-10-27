## 1. Version file

- [x] 1.1 ~~Edit `VERSION`: change `0.8.0` to `0.8.1`~~
  _(descoped — VERSION advanced to `0.9.0` via TRN-271 before this task was actioned)_

## 2. architecture.md — start.sh config discovery

- [x] 2.1 Fix `./start.sh` example command: `--config ~/ghostship.conf` →
  `--config ~/ghostship.yaml` ✓ (confirmed in place)
- [x] 2.2 Replace three-item config discovery list with the two actual paths
  `start.sh` uses ✓ (confirmed in place)

## 3. portal.md — Setup section

- [x] 3.1 Replace `# ghostship.conf` / `./install.sh --config ./ghostship.conf`
  with `ghostship.yaml` equivalents ✓ (confirmed in place)

## 4. configuration.md — KC_BASE_IMAGE description

- [x] 4.1 Update `KC_BASE_IMAGE` description to reference stable tag
  _(superseded by TRN-274 H-10 — updated further to KC 0.10.0 multi-arch digest)_

## 5. README.md — model access note

- [x] 5.1 Clarify kiro-backend scope of the `claude-haiku-5-5` Pro-subscription
  callout ✓ (confirmed: "on the kiro backend… crews on other backends resolve
  models via their own namespace")

## 6. release-notes-0.6.0.md — annotate resolved limitations

- [x] 6.1 Add `> **Resolved in v0.8.1:**` callout before Captain autopilot
  limitation (line ~126) ✓ (confirmed in place)
- [x] 6.2 Add same resolved callout to Known Limitations section (line ~214) ✓
  (confirmed in place)
- [x] 6.3 Add auth migration note near `GA_CREW_ANTHROPIC_API_KEY` references ✓
  (confirmed in place — v0.8.0+ note at lines 64 and 77)

## 7. docs/release-notes-0.8.1.md — create new file

- [x] 7.1 Create file with Overview section ✓
- [x] 7.2 Add New section covering `ghostship-spawn` (TRN-263) and academy
  backend delivery (TRN-264) ✓
- [x] 7.3 Add Fixed section covering four hotfix items ✓
- [x] 7.4 Add Resolved Limitations section ✓

## 8. Verification

- [x] 8.1 No remaining `ghostship.conf` refs in `docs/architecture.md` or
  `docs/portal.md` Setup section ✓ (confirmed)
- [x] 8.2 ~~Confirm `VERSION` reads `0.8.1`~~
  _(descoped — see 1.1)_
- [x] 8.3 `docs/release-notes-0.8.1.md` exists and linked from README Further
  reading ✓ (confirmed)
