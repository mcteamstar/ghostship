## 1. Version file

- [ ] 1.1 Edit `VERSION`: change `0.8.0` to `0.8.1`

## 2. architecture.md — start.sh config discovery

- [ ] 2.1 In `docs/architecture.md`, fix the `./start.sh` example command: change
  `--config ~/ghostship.conf` to `--config ~/ghostship.yaml`
- [ ] 2.2 Replace the three-item config discovery list (lines 184-186) with the two
  actual paths `start.sh` uses:
  1. `config/ghostship.yaml` (repo directory)
  2. macOS: `~/Library/Application Support/ghost-academy/ghostship.yaml` /
     Linux: `${XDG_CONFIG_HOME:-$HOME/.config}/ghost-academy/ghostship.yaml`

## 3. portal.md — Setup section

- [ ] 3.1 In `docs/portal.md` Setup section, replace the `# ghostship.conf` comment
  and `./install.sh --config ./ghostship.conf` example with `# ghostship.yaml` and
  `./install.sh --config ./ghostship.yaml`

## 4. configuration.md — KC_BASE_IMAGE description

- [ ] 4.1 In `docs/configuration.md`, update the `KC_BASE_IMAGE` table-row description
  to reference the stable `0.9.0` tag instead of the insider qualifier `0.9.0-insider.4`

## 5. README.md — model access note

- [ ] 5.1 In `README.md`, add a short parenthetical or qualifier to the
  `claude-haiku-5-5` Pro-subscription callout box to clarify it applies to the
  kiro backend default; crews on other backends resolve models via their own
  namespace

## 6. release-notes-0.6.0.md — annotate resolved limitations

- [ ] 6.1 In `docs/release-notes-0.6.0.md`, add a `> **Resolved in v0.8.1:**`
  callout before the "Captain autopilot does not work on Claude or Codex backend crews"
  limitation under the "Known limitation" section (line ~122) explaining that
  `ghostship-spawn` (TRN-263) resolved this
- [ ] 6.2 Add the same resolved callout to the "Known Limitations" section at the
  bottom of the file (line ~208) for the Captain autopilot item
- [ ] 6.3 Add a short note near the `GA_CREW_ANTHROPIC_API_KEY` references (lines 59,
  82) that credential management moved to `ghostship auth login` in v0.8.0 and the
  key is no longer used; link to auth.md

## 7. docs/release-notes-0.8.1.md — create new file

- [ ] 7.1 Create `docs/release-notes-0.8.1.md` with an Overview section summarising
  the hotfix nature of the release (four fixes + two feature additions)
- [ ] 7.2 Add a "New" section covering `ghostship-spawn` Academy skill (TRN-263) and
  academy backend delivery to all harnesses (TRN-264), sourced from CHANGELOG
- [ ] 7.3 Add a "Fixed" section covering the four hotfix items from CHANGELOG v0.8.1:
  gateway error detail, Caddy CA cert volume name, skill bytecode exclusion, Raven
  order-template wording
- [ ] 7.4 Add a "Resolved Limitations" section listing the Captain autopilot and Claude
  attribution limitations from 0.6.0/0.8.0 that are now closed

## 8. Verification

- [ ] 8.1 Confirm no remaining `ghostship.conf` references in `docs/architecture.md`
  or `docs/portal.md` Setup section (grep check)
- [ ] 8.2 Confirm `VERSION` reads `0.8.1`
- [ ] 8.3 Confirm `docs/release-notes-0.8.1.md` exists and is linked from
  `README.md` Further reading section (or add the link)
