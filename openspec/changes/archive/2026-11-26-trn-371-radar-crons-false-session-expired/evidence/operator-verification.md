# TRN-371 scheduled-jobs removal: operator verification checklist

Task 4.1 in `tasks.md` is open because it needs a portal running with Caddy, a fleet with a running crew, and a browser. An agent cannot run it. This checklist gives the operator the steps. Every command, path and flag comes from the repository.

**Status:** open. The Admiral ruled on 2026-11-26 that this operator check does not block review or archive of the change. Task 4.1 stays unticked in `tasks.md` until the operator records a pass in the results table at the end of this file.

Conventions used below:

- `$REPO` is the path of the ghostship checkout on the operator host, on the `release/0.13.2` branch at the commit that lands this change, or a later commit.
- `$RADAR_URL` is the browser address of the portal, for example `https://your-portal-hostname/` or `http://localhost:64057/`. `docs/radar.md` gives both forms.
- Run commands from `$REPO` unless a step says otherwise.
- Record the result in the table at the end. Do not tick the `tasks.md` checkbox on the basis of this file. The operator ticks it after recording a pass.

---

## Task 4.1: Radar crew detail after the scheduled-jobs removal

**Verify (from tasks.md):** run `ghostship upgrade`, open Radar through Caddy against a fleet with a running crew, and expand it. There is no Scheduled jobs section and no "Session expired" text. Active tasks, Captain, Credentials and Mailbox subjects still load. The browser shows no request to `/crews/<id>/api/crons`.

**Host prerequisites**

- A portal installed from this repository, with Podman and Caddy set up as the installer sets them up.
- At least one crew whose status is `running` in the Radar table. The removed request only ran for running crews, so a stopped crew does not exercise it.
- A browser with developer tools, such as Chromium or Firefox.
- If `GA_API_KEY` is set, a portal login. Radar redirects to `/dashboard/login` until you sign in.

**Steps**

1. Upgrade the portal to this change:
   ```
   cd "$REPO"
   ghostship upgrade
   ```
   The command asks for confirmation. `ghostship upgrade --yes` skips the prompt. Expected: the upgrade finishes without error.
2. Open Radar at `$RADAR_URL` and wait for the first fleet load. The status area shows `Refreshed at:` with a time.
3. Click the row of a running crew to expand it. The panel shows, in order: an `Image:` line, the `Active tasks` heading, the `Captain` heading (only when the crew has a Captain schedule), the `Credentials` heading and the `Mailbox subjects` heading.
4. Check the expanded panel:
   - There is no `Scheduled jobs` heading.
   - The text `Session expired, sign in again` does not appear in the panel or in the status area.
   - `Active tasks` shows its tasks or `No active tasks.`. `Mailbox subjects` shows its subjects or `No messages.` in each empty mailbox.
   - `Credentials` shows its Refresh auth button.
   - Neither `Active tasks unavailable.` nor `Mailbox subjects unavailable.` appears. If one appears, record which section and check the transport log before you record a fail.
5. Check the requests the browser makes. Open the Network tab in developer tools, reload the page, expand the running crew, and filter the list by `/crews/`. Expected: no rows. The removed section requested a path under `/crews/`, and nothing in Radar requests that prefix now.
6. Collapse the crew, expand it again, and wait for one fleet refresh (the table polls every five seconds). Expected: the open panel keeps the same sections, and no new `/crews/` request appears in the Network tab.

**Assumptions:**

- `ghostship upgrade` installs the latest release tag, according to its usage text. If this change is not in a release tag yet, the upgrade does not bring it in. Install it the way the team installs unreleased builds on the operator host. The repository does not name that path, so the operator uses their own.
- A crew without a Captain schedule does not show the `Captain` heading. That is correct, not a failure.
- Step 5 uses the browser's developer tools. A `curl` request does not run the page's scripts, so it cannot show what the browser asks for.

**Record:** the `ghostship upgrade` result, the name of the crew you expanded, the headings you saw, the Network-tab result from step 5, and pass or fail for each check in steps 4 and 6.

---

## Results table for the operator

| Task | Date | Host | Pass or fail | Notes |
|:-----|:-----|:-----|:-------------|:------|
| 4.1 Radar crew detail after the scheduled-jobs removal | | | | |

When the row is a pass, the operator ticks task 4.1 in `tasks.md`. Do not tick it for a row that is not recorded as a pass.

---

## Node 24 pin

**Change:** the Radar UI build pin changed from Node 26 to Node 24 by admiral decision. `radar/Containerfile` now builds from `node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5`.

**Not testable in the crew:** the image build. The crew has no Podman, so the digest was not pulled and no `ga-radar` image was built. The crew did run `npm ci` (no engine warning), `npm run typecheck`, `npm test` and `npm run build` in `radar/web` on Node v24.22.3, and all passed.

**Steps**

1. Build the image through the upgrade path:
   ```
   cd "$REPO"
   ghostship upgrade
   ```
   Expected: the output shows `Building localhost/ga-radar:latest ...`, the build finishes, and the installer prints `✓ ga-radar image built`. The Containerfile runs `npm ci`, `npm run typecheck` (`tsc --noEmit`) and `npm run build` (`vite build`) as build steps, so a finished build means all three succeeded on `node:24-alpine`. As in the Task 4.1 assumptions, `ghostship upgrade` installs the latest release tag, so the pin must be in that tag.
2. Confirm the pinned digest is Node 24:
   ```
   podman run --rm --entrypoint node docker.io/library/node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 --version
   ```
   Expected: a version that starts with `v24.`.
3. Confirm the runtime image still has no Node or npm:
   ```
   podman run --rm --entrypoint sh localhost/ga-radar:latest -c 'command -v node || echo "no node binary"; command -v npm || echo "no npm binary"; ls -d /app/node_modules 2>/dev/null || echo "no node_modules"; ls /app'
   ```
   Expected: `no node binary`, `no npm binary`, `no node_modules`, and `/app` lists `requirements.txt`, `server.py` and `static`.

**Record:** the `ghostship upgrade` result, the version printed in step 2, and pass or fail for steps 1 and 3. The step 2 version is what the "pending its first real build" note on `node-radar-build-image` in `dependencies.yaml` is waiting for.
