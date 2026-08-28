## 1. install.sh — copy academy/ and crews/ into the data volume

- [ ] 1.1 Add a copy step in `install.sh` after the image build phase: use `rsync -a --delete` (with a `cp -r` fallback if rsync is absent) to copy `${GHOSTSHIP_DIR}/academy/agents`, `academy/skills`, `academy/steering`, `academy/policies`, `academy/orders` into `${DATA_DIR}/academy/` and `${GHOSTSHIP_DIR}/crews` into `${DATA_DIR}/crews/`
- [ ] 1.2 Ensure the copy step runs before the `compose.yml` generation block, so the destination paths are present when `compose.yml` is written
- [ ] 1.3 Add a log line confirming the copy (`echo "✓ academy/ and crews/ copied to ${DATA_DIR}"`)

## 2. install.sh — update generated compose.yml volume entries

- [ ] 2.1 In the `cat > "${DATA_DIR}/compose.yml" <<COMPOSE_EOF` heredoc, replace the six `${GHOSTSHIP_DIR}/academy/*` and `${GHOSTSHIP_DIR}/crews` volume lines with the corresponding `${DATA_DIR}/academy/agents`, `${DATA_DIR}/academy/skills`, `${DATA_DIR}/academy/steering`, `${DATA_DIR}/academy/policies`, `${DATA_DIR}/academy/orders`, and `${DATA_DIR}/crews` paths (all still `:ro`)
- [ ] 2.2 Verify no other references to `${GHOSTSHIP_DIR}/academy` or `${GHOSTSHIP_DIR}/crews` remain in the generated compose output

## 3. Validation

- [ ] 3.1 Run `./install.sh` on a local machine and confirm `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` are populated after install
- [ ] 3.2 Confirm the generated `${DATA_DIR}/compose.yml` contains no bind-mounts referencing the repo path (`GHOSTSHIP_DIR`)
- [ ] 3.3 Move (or rename) the repo directory after install and confirm `start.sh` starts the transport successfully without errors about missing mounts
- [ ] 3.4 Edit a file under `academy/` in the repo, re-run `./install.sh`, and confirm the change is visible in `${DATA_DIR}/academy/`
- [ ] 3.5 Delete a file from `academy/` in the repo, re-run `./install.sh`, and confirm the deleted file is absent from `${DATA_DIR}/academy/` (validates `--delete` behaviour)

## 4. Documentation

- [ ] 4.1 In `docs/configuration.md`, add a note (under "Extending the crew image" or a new "Updating academy/ and crews/" section) that `academy/` and `crews/` are snapshotted into the data volume at install time and that changes require re-running `./install.sh`
- [ ] 4.2 In `README.md`, add the same reinstall-to-update note alongside the existing "Extending the crew image" instructions
