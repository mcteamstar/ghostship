# TRN-371 operator verification checklist

Seven tasks in `tasks.md` are open because they need a host with Podman, Caddy, a running fleet, a host without Node, and a browser. This checklist gives the operator the steps for each one. Every command, path and flag comes from the repository. Where a step depends on something the repository does not state, the step says so.

Conventions used below:

- `$REPO` is the path of the ghostship checkout on the operator host, on the `release/0.13.2` branch at commit `9144aede` or later.
- `$RADAR_URL` is the browser address of the portal, for example `https://your-portal-hostname` or `http://localhost:64057`. `docs/radar.md` gives both forms.
- Run commands from `$REPO` unless a step says otherwise.
- Record each result in the table at the end. Do not tick a `tasks.md` checkbox on the basis of this file; the operator ticks it after recording a pass.

---

## Task 1.2: Containerfile is multi-stage, Node-free at runtime

**Verify (from tasks.md):** `podman build radar/` succeeds, the runtime image has no `node` binary or `node_modules`, the built `index.html` has no inline `<script>`, and a deliberate type error fails the build.

**Host prerequisites**

- Podman installed. `podman --version` prints a version.
- Network access to the `docker.io` registry for `node:26-alpine` and `python:3.12-slim`, and to the npm registry.
- The Node pin is `radar/Containerfile`, stage `web-build`, digest `sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5`. The same digest is in the Containerfile, so no value needs to be looked up.

**Steps**

1. Build the image the same way the installer does (`bin/lib/install_main.py`, function `_build_radar_bundle`):
   ```
   cd "$REPO"
   podman build -t localhost/ga-radar:verify radar/
   ```
   Expected: the build ends with `Successfully tagged localhost/ga-radar:verify` (or the Podman equivalent), exit code 0.
2. Confirm the runtime image has no Node and no `node_modules`:
   ```
   podman run --rm --entrypoint sh localhost/ga-radar:verify -c 'command -v node || echo "no node binary"; ls -d /app/node_modules 2>/dev/null || echo "no node_modules"; ls /app'
   ```
   Expected: `no node binary`, `no node_modules`, and `/app` lists `server.py`, `requirements.txt` and `static`.
3. Confirm the built page has no inline script:
   ```
   podman run --rm --entrypoint sh localhost/ga-radar:verify -c 'grep -c "<script>" /app/static/index.html || true'
   ```
   Expected: `0`. The page's script tag is `<script type="module" crossorigin src="/static/assets/...">`, which has attributes and is not inline.
4. Confirm a deliberate type error fails the build. On a scratch copy so the checkout stays clean:
   ```
   rm -rf /tmp/radar-typeerror && cp -r "$REPO/radar" /tmp/radar-typeerror
   printf '\nconst __verify: number = "not a number";\nexport {};\n' >> /tmp/radar-typeerror/web/src/main.tsx
   podman build -t localhost/ga-radar:typeerror /tmp/radar-typeerror
   ```
   Expected: the build stops at the `RUN npm run typecheck && npm run build` step with a TypeScript error, and the exit code is non-zero.
5. Remove the scratch files: `rm -rf /tmp/radar-typeerror`.

**Assumptions:** The test in step 4 assumes `main.tsx` accepts an appended statement. If `main.tsx` changes, pick any `.tsx` file under `web/src/`. The grep in step 3 is a lightweight check of the built file; for a full check, read the file.

**Record:** pass or fail for each of the four checks, the image ID from step 1, and the exit code from step 4.

---

## Task 1.3: installer builds the bundle on a host without Node

**Verify (from tasks.md):** `_build_images` builds the new Containerfile for both `./install.sh` and `ghostship upgrade`, and a failure reports "Radar bundle build failed" while the existing `ga-radar:latest` stays in place. Check with the fake-Podman installer test, and with a real `./install.sh` run on a host without Node.

**Host prerequisites**

- A host with Podman and no Node on `PATH`. Check with `command -v node || echo "node absent"`. Expected: `node absent`. The development checkout used for this review has Node 24 at `/usr/bin/node`, so it does not qualify.
- Python 3.12 with the transport requirements installed (`pip install -r transport/requirements.txt`, as in `.github/workflows/test.yml`).

**Steps**

1. Run the fake-Podman installer tests from the unit suite:
   ```
   cd "$REPO"
   .venv/bin/python -m pytest tests/unit/test_radar_image_build.py -q
   ```
   If the venv does not exist, use `python3 -m pytest` with the transport requirements installed. Expected: all tests pass. The two tests that assert `Radar bundle build failed` (`test_radar_image_build.py`) pass.
2. Record the current Radar image ID, if any: `podman image inspect localhost/ga-radar:latest --format '{{.Id}}' 2>/dev/null || echo "no ga-radar image"`.
3. Run the installer on the host without Node. `./install.sh` is the shim in the repository root, and it runs `bin/install.sh`. Use the same flags the operator used for the original install, or none. Expected: the output contains `Building localhost/ga-radar:latest ...`, the build completes, and the installer ends with its normal success message.
4. Check the image was built and the bundle is inside it:
   ```
   podman run --rm --entrypoint sh localhost/ga-radar:latest -c 'ls /app/static/index.html && ls /app/static/assets | head -3'
   ```
5. Failure path. Check that a failed build leaves the image in place. The repository does not provide a switch to force an `npm ci` failure on a real host, so use a deliberate typecheck failure as in task 1.2 step 4 and run `podman build` against the scratch copy, or rebuild with `podman build -t localhost/ga-radar:latest /tmp/radar-typeerror` after the change. Then compare the image ID from step 2. Expected: the image ID is unchanged. The installer message, when the installer runs the build, reads `Radar bundle build failed at '...'` and names the step.

**Assumptions:** The repository does not provide a way to make `npm ci` fail on purpose. Step 5 covers the typecheck failure path, and the `npm ci` failure text is covered by the fake-Podman test in step 1. The operator should state in the results table which of the two was exercised. Flags for `./install.sh` depend on the original install and are not listed here.

**Record:** the fake-Podman test result, the image IDs before and after step 5, the installer's final line, and whether Node was absent.

---

## Task 1.4: CI workflow runs the frontend commands

**Verify (from tasks.md):** `.github/workflows/test.yml` parses, and the job runs the Node setup step and the frontend test and type-check commands.

**Host prerequisites**

- Python with PyYAML available, or the vendored copy at `bin/lib/vendor/yaml` (the installer uses it).
- Access to the hosted CI for this repository. The workflow is named `tests` (`name: tests` in the file).

**Steps**

1. Check that the YAML parses:
   ```
   cd "$REPO"
   python3 -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/test.yml')); print('parsed; jobs:', list(d['jobs']))"
   ```
   Expected: `parsed; jobs:` followed by a list that includes the unit job and `integration-tests`. If PyYAML is missing, `pip install pyyaml` or use the vendored copy with `PYTHONPATH=bin/lib/vendor python3 -c "import yaml ..."`.
2. Check the frontend steps are in the unit job. Look for the step names `Set up Node for the Radar UI`, `Radar UI type check` and `Radar UI tests` in `.github/workflows/test.yml`. Each should run `npm ci`, `npm run typecheck` or `npm test` from `radar/web`.
3. Run the same commands locally to confirm they pass, from `radar/web`:
   ```
   cd "$REPO/radar/web"
   npm ci
   npm run typecheck
   npm test
   ```
   Expected: `npm run typecheck` exits 0 and `npm test` reports all tests passing.
4. On the hosted CI, open the latest `tests` run for branch `release/0.13.2` and confirm the three Radar steps show green. If the operator uses the GitHub CLI, `gh run list --workflow tests --branch release/0.13.2` lists the runs.

**Assumptions:** The operator's CI is the GitHub Actions setup in the repository. The `gh` step assumes the GitHub CLI is installed and signed in. Step 3 needs Node 26 to match `radar/web/.nvmrc`; a different Node version is noted in the results.

**Record:** the YAML parse output, the local `npm` results, and the CI run URL and state.

---

## Task 5.3: contributor docs and dev loop

**Verify (from tasks.md):** `CONTRIBUTING.md` documents the frontend commands and a dev proxy against a running fleet, and `docs/radar.md` names the current files. Each documented command runs as written.

**Host prerequisites**

- Node 26 (the pin in `radar/web/.nvmrc`). Use `nvm use` or `fnm use` in `radar/web` if the operator manages Node versions this way.
- A running portal for the dev proxy. The default target is `http://localhost:64057`, set in `radar/web/vite.config.ts`.

**Steps**

1. Read the section `## Radar UI (frontend)` in `CONTRIBUTING.md`. Confirm the commands listed: `npm ci`, `npm run typecheck`, `npm test`, `npm run build`, `npm run dev`.
2. From `radar/web`, run each command in that order:
   ```
   cd "$REPO/radar/web"
   npm ci
   npm run typecheck
   npm test
   npm run build
   ```
   Expected: each exits 0. `npm run build` writes `radar/web/dist`, which is in `radar/web/.gitignore`.
3. Start the dev server against the running fleet:
   ```
   RADAR_PROXY_TARGET=http://localhost:64057 npm run dev
   ```
   Expected: Vite prints `Local: http://localhost:5173/`. Open that address; the page shows the fleet table after a poll. If the portal is elsewhere, set `RADAR_PROXY_TARGET` to its URL, as `CONTRIBUTING.md` shows.
4. Check the documented Python docs-parity tests still pass: `cd "$REPO" && bash scripts/run.sh --unit`. Expected: the unit suite passes. The script is in `scripts/run.sh` and is the command `CONTRIBUTING.md` names.
5. Check `docs/radar.md` for module names. Search it for `render.js`, `state.js` and `main.js`: `grep -n -E "render\.js|state\.js|main\.js" docs/radar.md`. Expected: no matches.

**Assumptions:** Step 3 needs a running portal; without one the page shows an error state, which still proves the dev server runs. `scripts/run.sh --unit` also runs the rest of the unit suite and takes about a minute.

**Record:** the result of each command, whether the dev server reached a fleet, and the grep output.

---

## Task 5.4: parity checkpoint against the old UI

**Verify (from tasks.md):** build and start `ga-radar` through Caddy against a running fleet, then walk the old and new UI side by side. Fleet table, sections, sort, filter, expand, deep link, copy, Refresh auth and session expiry must match. List every field the old detail shows, and record each difference as a defect.

**Host prerequisites**

- A running fleet, with at least one running crew and one stopped crew.
- A browser, with the old UI available. The old UI is the code at commit `764cc56d`, which is the base of this change.
- Caddy running as part of the portal (`bin/lib/caddy_install.py` writes its routes). The Caddy admin API is a Unix socket at `/run/ga-portal-admin/admin.sock`, as set in `bin/lib/caddy_install.py`, not the port 2019 default.

**Steps**

1. Build and start the new UI. Follow the install steps in `docs/manual-install.md` or run `./install.sh` again, then restart the portal with `./bin/start.sh`. The `ga-radar` image is `localhost/ga-radar:latest` (see `bin/lib/compose.py`).
2. Build the old UI into a second image, from a git worktree so the checkout is not changed:
   ```
   cd "$REPO"
   git worktree add /tmp/ghostship-764cc56d 764cc56d
   podman build -t localhost/ga-radar:pre-trn371 /tmp/ghostship-764cc56d/radar
   ```
   Expected: the build succeeds. The old Containerfile has no Node stage, so it builds quickly.
3. To run the old UI in place of the new one for the comparison, tag the images and restart the `ga-radar` service:
   ```
   podman tag localhost/ga-radar:latest localhost/ga-radar:trn371
   podman tag localhost/ga-radar:pre-trn371 localhost/ga-radar:latest
   ```
   Then restart `ga-radar` through the portal's compose file under the data directory (`DATA_DIR`, see `docs/configuration.md`): `podman-compose -f "$DATA_DIR/compose.yml" up -d ga-radar`.
   **Assumption:** the repository does not give the exact restart command for the running portal. The compose file path and `podman-compose` usage follow `bin/start.sh`, but confirm the service name with `grep -n "ga-radar" "$DATA_DIR/compose.yml"`.
4. Walk both UIs in the browser against `$RADAR_URL`. For each, check:
   - the fleet table: running rows first, then the `Inactive` divider, then stopped rows
   - the default order (newest created first), and the Last Task sort (three clicks cycle through none, descending, ascending)
   - the filter, with a crew ID and with a non-matching string
   - expanding a row with a click and with Enter or Space; the detail sections; the dashboard link
   - the copy button for a crew ID, which must not expand the row
   - the deep link `#crew=<id>` on a fresh page load
   - Refresh auth on a running crew, and on a stopped crew
   - session expiry, by signing out in another tab and then refreshing
5. Write a list of every field the old detail shows. Read the old detail code with `git show 764cc56d:radar/static/render.js` (look at `renderDetail` and `renderAgents`, and at the crons and mailbox loaders in the same file) and list each field it draws. Check each one is present in the new detail. Record any field that is missing or different as a defect.
6. Restore the new UI: `podman tag localhost/ga-radar:trn371 localhost/ga-radar:latest`, restart `ga-radar`, and remove the worktree with `git worktree remove /tmp/ghostship-764cc56d`.

**Known differences to check, which are deliberate:** the agent list shows once; the dashboard link does not toggle the row; an invalid timestamp shows an em dash; a missing mailbox shows `unavailable`; a deep link opens the row and loads its detail. The operator should confirm each one and record it as accepted or as a defect.

**Record:** for each walk item, pass or fail with the difference noted; the field list from step 5; the image tags used.

---

## Task 6.8: accessibility pass

**Verify (from tasks.md):** accessible names, focus order, `aria-expanded` on the expand control, keyboard access to copy, sort, filter and links, and live-region announcements. The automated part is the axe test in `radar/web/test/app/accessibility.test.tsx`. The manual part is a keyboard-only walkthrough.

**Host prerequisites**

- A browser with developer tools. Chromium or Firefox is enough for the keyboard pass.
- Optional: a screen reader (NVDA on Windows, VoiceOver on macOS). The repository does not specify one, so the operator picks it and records it.

**Steps**

1. Run the automated checks:
   ```
   cd "$REPO/radar/web"
   npm test -- test/app/accessibility.test.tsx
   ```
   Expected: both accessibility tests pass. The axe test names the rules it ran and reports no violations. The colour-contrast rule is off in that test because jsdom cannot measure colour; contrast is covered by `openspec/changes/trn-371-migrate-radar-to-react/evidence/contrast.md`.
2. Keyboard-only walkthrough at `$RADAR_URL`, with the mouse unplugged or not used:
   1. Press Tab from the top of the page. Focus moves through the page in visible order: filter, sort button, then each row's expand button and copy button.
   2. On the filter, type a crew ID. The filtered rows change, and the status line stays visible.
   3. Focus the `Last Task` sort button and press Enter. The header's `aria-sort` changes; check with the developer tools accessibility panel.
   4. Focus a crew's expand button. Press Enter, then Space. Each press toggles the detail, and the button reports `aria-expanded` true and false.
   5. Open the detail. Tab to `Refresh auth`, press Enter, and check the `Still working…` note and the result are announced (a `role="status"` region).
   6. Focus a copy button and press Enter. The confirmation mark shows, and the row does not expand.
   7. Tab to a dashboard link, if the crew has one, and press Enter. It opens in a new tab.
3. Check accessible names. In the developer tools accessibility tree, each expand button is named `Expand details for <crew>` or `Collapse details for <crew>`, and each copy button is named `Copy crew ID <crew>`. Each detail section is a level-2 heading.
4. If a screen reader is used, record which one and its version. Check that the status line announces a fleet error.

**Record:** the axe test result, the walkthrough result for each step, the screen reader used (if any), and any control that could not be reached by keyboard.

---

## Task 7.1: final integration check through Caddy

**Verify (from tasks.md):** build and start `ga-radar`, load it through Caddy against a running fleet, and walk the `radar-ui` scenarios (poll, open detail across a poll, filter, deep link, session expiry, dark mode, 360 px width). `GET /static/main.js` returns 404, `GET /` returns `no-cache`, a hashed asset returns `immutable`, and the existing Caddy routes needed no change.

**Host prerequisites**

- The image from `./install.sh` (task 1.3) running, with the portal and Caddy up.
- A browser for the scenario walk.
- If `GA_API_KEY` is set, the portal redirects to `/dashboard/login`. Log in once in the browser and copy the `gs_session` cookie value from the developer tools for the `curl` checks below (see `docs/radar.md`, "Accessing Radar").

**Steps**

1. Check the removed module is 404:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' "$RADAR_URL/static/main.js"
   ```
   Expected: `404`.
2. Check the page is revalidated:
   ```
   curl -s -D - -o /dev/null "$RADAR_URL/" | grep -i '^cache-control'
   ```
   Expected: `cache-control: no-cache`.
3. Find a hashed asset from the page and check its cache policy:
   ```
   ASSET=$(curl -s "$RADAR_URL/" | grep -o '/static/assets/[^"]*\.js' | head -1)
   echo "$ASSET"
   curl -s -D - -o /dev/null "$RADAR_URL$ASSET" | grep -i '^cache-control'
   ```
   Expected: `cache-control: public, max-age=31536000, immutable`. The asset name comes from the page, so it changes with each build.
4. Check a conditional request keeps the immutable policy (the 304 defect fixed in commit `e63650f3`):
   ```
   ETAG=$(curl -s -D - -o /dev/null "$RADAR_URL$ASSET" | grep -i '^etag' | cut -d' ' -f2- | tr -d '\r')
   curl -s -D - -o /dev/null -H "If-None-Match: $ETAG" "$RADAR_URL$ASSET" | grep -i -E '^HTTP|^cache-control'
   ```
   Expected: `HTTP/... 304` and `cache-control: public, max-age=31536000, immutable`.
5. Check an unknown API path is 404 and not the page:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' "$RADAR_URL/api/unknown"
   ```
   Expected: `404`.
6. Check the existing Caddy routes. The route set is generated by `bin/lib/caddy_install.py` and sends `/`, `/api/crews` and `/api/crews/*` and `/static/*` to `ga-radar:8080`. Read the live configuration through the admin socket:
   ```
   curl -s --unix-socket /run/ga-portal-admin/admin.sock http://localhost/config/ | grep -o '"/static/\*"' | head -1
   ```
   Expected: the route `"/static/*"` is present. **Assumption:** the socket path and the `localhost` host in that URL come from `bin/lib/caddy_install.py`; if Caddy on the host uses a different admin setting, read the route set from the file the installer wrote and note the difference.
7. Walk the `radar-ui` scenarios in the browser at `$RADAR_URL`:
   - poll: the status line updates every five seconds
   - an open detail stays open across a poll, with its loaded sections
   - the filter matches a crew ID and stays set across a poll
   - a deep link `#crew=<id>` opens the row after the first load
   - session expiry: sign out in another tab, then refresh and check the `Session expired, sign in again` state
   - dark mode: switch the OS or the browser to dark appearance and check the page switches without a reload
   - 360 px width: in the developer tools responsive mode at 360 px wide, the page does not scroll sideways, and every crew shows its name, status and expand control
8. Record the results.

**Record:** the output of steps 1 to 5, the `$ASSET` name, and pass or fail for each scenario in step 7.

---

## Results table for the operator

Fill in one row per task. Leave a row blank if the task was not run.

| Task | Date | Host | Pass or fail | Notes |
|:-----|:-----|:-----|:-------------|:------|
| 1.2 Containerfile multi-stage | | | | |
| 1.3 installer builds bundle, failure path | | | | |
| 1.4 CI workflow runs frontend commands | | | | |
| 5.3 contributor docs and dev loop | | | | |
| 5.4 parity checkpoint against old UI | | | | |
| 6.8 accessibility pass | | | | |
| 7.1 final integration through Caddy | | | | |

When every row is a pass, the operator ticks the matching checkbox in `tasks.md` and archives the change in a later step. Do not tick a box for a row that is not recorded as a pass.
