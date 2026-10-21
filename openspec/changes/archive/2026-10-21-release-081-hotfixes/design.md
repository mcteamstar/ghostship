# Design

## Context

See proposal.md for why. Relevant current code:

- `_crew_api_with_recovery` (`transport/lifecycle.py`) catches `httpx.HTTPStatusError`, runs phase 1 (cookie refresh) and phase 2 (restart), and on giving up raises `CrewUnresponsiveError("crew … is unresponsive — transport attempted …")`. The last `HTTPStatusError`'s response is in scope but discarded.
- `AcademyLoader._stage_skills` (`transport/academy.py`) tars every regular file under each selected skill directory.
- The portal data volume is declared as `ga-portal-data` in `compose.yml`, and Compose runs with `--project-name ga`, so Podman creates `ga_ga-portal-data`. `ghostship` (status) and `bin/install.sh` (post-install CA path) both inspect `ga-portal-data`.
- `tests/e2e/helpers.py` defaults `GHOSTSHIP_PODMAN_SOCKET` to `/run/user/1000/ghost-academy/podman.sock`.

## Goals / Non-Goals

**Goals:** each fix is small, independently revertable, and covered by a test where one makes sense.

**Non-Goals:** changing which status codes trigger recovery (see proposal, out of scope); renaming the Compose volume, which would orphan existing Caddy CA data.

## Decisions

### 1. Error detail is appended, not substituted
Keep the existing `CrewUnresponsiveError` message (callers and tests match on "unresponsive") and append `Last gateway response: HTTP <status>: <body>`, with the body passed through a redaction helper and truncated to 500 characters. Keep the last `HTTPStatusError` in a local variable across phases so it's available at every give-up point. Redact the crew's current cookie value from the registry and any `mc_token_<port>=…` pattern.

When the last error was a 4xx, replace the trailing "Suggestion: check crew status with crews() …" with "the crew gateway rejected the request; see the response above". That suggestion points at crew health, which is misleading when the gateway is up and refusing the request.

*Alternative:* a new error type for gateway 4xx. Rejected for now, because it changes the recovery contract that this change leaves alone.

### 2. Bytecode filter at staging
`_stage_skills` skips any path with a `__pycache__` component and any `*.pyc` file. A `.gitignore`-style generic filter is overkill for one known source of noise.

### 3. Volume lookup tries the Compose name first
Inspect `ga_ga-portal-data`, then fall back to `ga-portal-data`, in both the CLI and `install.sh`. This covers today's installs and any older install where the volume was created by hand. The project prefix comes from the same `ga` value passed to `--project-name`.

### 4. macOS socket default resolved at runtime
On macOS, `tests/e2e/helpers.py` resolves the socket with `podman machine inspect <GA_MACHINE_NAME or ghost-academy> --format '{{.ConnectionInfo.PodmanSocket.Path}}'`, falling back to the Linux default if that fails. The dedicated machine is rootless (`Rootful=false`), and that path is the host-side forwarded API socket for the same rootless instance the transport and crew containers run under (for example `$TMPDIR/podman/ghost-academy-api.sock`), so the test talks to the right Podman. If the machine is ever made rootful, the same field points at the rootful socket, which is where the containers would then live. `GHOSTSHIP_PODMAN_SOCKET` still overrides it. Hard-coding a macOS path would break for a non-default user or machine name.

### 5. Template guidance is one shared sentence
Add the same short paragraph to both order templates near their store-resolution step, and extend the existing Raven prompt contract test to assert it appears in each resolved template.

## Risks / Trade-offs

- [Gateway bodies could carry sensitive text other than the cookie] → They are KiroCrew error messages. Truncate to 500 characters and redact the cookie and token patterns. Review the first real examples.
- [Volume fallback hides a genuinely missing volume] → Both names failing still prints the existing "not found" message.
- [The CA path is a VM path on macOS] → `podman volume inspect` returns the mountpoint inside the Podman VM, so on a Mac the printed `root.crt` path isn't on the host. The fix still satisfies `transport/tls`, which only requires the path to be shown. Making it usable on macOS (for example printing a `podman machine ssh` or `podman cp` command) is a follow-up.
