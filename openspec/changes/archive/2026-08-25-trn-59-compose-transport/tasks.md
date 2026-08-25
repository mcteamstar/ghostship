## 1. Podman version check in install.sh

- [x] 1.1 Add a version check after the Podman installation step: parse `podman --version`, compare against 4.4.0, and exit with a clear error if below.

## 2. Generate compose.yml in install.sh

- [x] 2.1 After the image build phase, write `${DATA_DIR}/compose.yml` via heredoc with all values interpolated: image, `container_name: ga-transport`, `restart: always`, `security_opt: [label=disable]`, ports, networks, volumes (including the Podman socket bind-mount), and all environment variables currently passed via `-e` to `podman run`.
- [x] 2.2 Use `networks: ga-net: external: true` since ga-net is created separately.
- [x] 2.3 Replace the `podman run` block with `_PODMAN_CMD compose --project-name ga -f "${DATA_DIR}/compose.yml" up -d`.

## 3. Simplify start.sh

- [x] 3.1 Remove the `podman start` + cold-boot `podman run` fallback block.
- [x] 3.2 After the "ensure Podman service is running" section, replace the container start logic with `podman compose --project-name ga -f "${DATA_DIR}/compose.yml" up -d` (using the correct `CONTAINER_HOST` / `--connection` prefix for the platform).
- [x] 3.3 If `compose.yml` doesn't exist (e.g. user never ran install.sh), print a clear error directing the user to run install.sh first.

## 4. Update uninstall.sh

- [x] 4.1 Replace the `podman stop ga-transport && podman rm ga-transport` block with `podman compose --project-name ga -f "${DATA_DIR}/compose.yml" down`.

## 5. Docs

- [x] 5.1 Update `docs/architecture.md` "Starting and restarting" section to mention the generated compose file and where it lives.
- [x] 5.2 Update `docs/manual-install.md` to note the Podman >= 4.4 requirement.

## 6. Verification

- [x] 6.1 Run `bash tests/run.sh --unit` — all tests pass.
- [x] 6.2 Deploy to vm23 and verify `install.sh` generates `compose.yml` and transport starts cleanly.
- [x] 6.3 Stop the transport manually, run `start.sh`, confirm it comes back up via compose.
- [x] 6.4 Reboot vm23, confirm `start.sh` (run manually) brings everything back via compose with no fallback needed.
