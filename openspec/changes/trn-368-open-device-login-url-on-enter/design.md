# Design

## Context

The CLI prints device-code instructions and then calls the shared `_poll_flow` loop. That loop also serves the authorization-code flow, so browser-on-Enter input handling must be enabled only for device-code login. The supported CLI platforms are macOS and Linux.

## Goals / Non-Goals

**Goals:**

- Detect a completed Enter keypress during an interactive device-code wait without pausing authentication polling.
- Open the printed login URL through Python's standard-library `webbrowser` module.
- Keep the URL visible and polling active if a browser cannot be launched.

**Non-Goals:**

- Automatically open the URL when login starts.
- Change authorization-code login or non-interactive behavior.
- Add a browser-launch dependency or change the transport API.

## Decisions

- Use `select` on terminal stdin only when stdin is a TTY, checking for a completed input line between authentication polls. A blank line triggers the browser; non-empty input is consumed without opening it. This avoids blocking the polling loop and avoids switching the terminal into raw mode. macOS and Linux support readiness checks on terminal stdin.
- Use `webbrowser.open(login_url)` to delegate to the operating system's configured default browser. This keeps OS-specific launch commands out of the CLI and avoids shell interpolation of the URL.
- Enable the input watcher only for device-code flows with a login URL. The shared polling loop must retain its current behavior for authorization-code flows. If `webbrowser.open` returns false or raises, print a concise diagnostic to stderr and continue polling; the original URL remains available above the wait prompt.
- Only show the Enter hint when stdin is a TTY and a login URL is available. In non-interactive runs, skip stdin monitoring entirely.

## Risks / Trade-offs

- [No graphical browser is available, or the browser opener fails] → Report the failure without ending authentication; the operator can use the printed URL manually.
- [Input is handled between poll requests] → Check stdin readiness during the wait interval so opening the browser does not require waiting for a full additional poll interval.

## Migration Plan

No migration is required. The change is local to the CLI and does not alter stored credentials, transport endpoints, or configuration.
