## Context

See `proposal.md` - Why for motivation. Relevant current implementation, in `transport/server.py`:

- `_handle_login_post` (~2403-2560) execs `kiro-cli login --use-device-flow [--license ...]` into a fresh `ga-login-<token>` container via a raw PTY+stdin socket (`podman.container_exec_pty_stdin`), then reads output for up to 15s, answering two known prompts by substring match on the accumulated text buffer (`"Start URL"`, then `"Region"`) before it looks for a `Open this URL: ...` line to extract the device code/URL. This substring-match-and-answer loop only knows about the IAM Identity Center prompt sequence.
- Confirmed live (this session, against a real `your-sso.awsapps.com` IDC login): with `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` set, this path works end-to-end — `POST /login` returns a valid device URL, `GET /login` reports `complete` after the browser flow, and `ga-kiro-auth` is written.
- Confirmed live: with no identity provider configured (Builder ID/free-tier path), `kiro-cli login --use-device-flow` instead prints an interactive `Select login method` menu (`Use with Builder ID` / `Use with Google` / `Use with GitHub` / `Use with Your Organization`, Builder ID pre-highlighted) before anything resembling `Start URL`. The loop doesn't recognize this text, never sends an answer, and the 15s deadline elapses, returning HTTP 500.
- A related bug (auth injected into a crew's SQLite DB not reaching its running kiro-cli/warm-pool processes) was suspected in this same session but turned out to already be fixed on `main` by `febeb6e`'s `crews/_base/orientation` + `crews/_base/graduation` image restructure, which restores `USER kirocrew` on the crew image (the gateway had been running as root, so its kiro-cli subprocess spawns read `/root/.local/share/kiro-cli/data.sqlite3` — never written by `_inject_auth` — instead of `/home/kirocrew/...`). Rebuilding against that fix and re-testing `launch` → `dispatch` end-to-end confirmed it works: no code change needed here.

## Goals / Non-Goals

**Goals:**
- Make `POST /login` succeed for the Builder ID (no identity provider) path, matching the already-documented "falls back to Builder ID" behavior in `crew-auth`'s "Identity provider configuration" requirement.
- Add regression coverage so this stays fixed.

**Non-Goals:**
- The auth-injection-to-working-dispatch issue — already fixed on `main`, not this change's concern.
- Handling identity providers/login methods beyond Builder ID, Google, GitHub, Your Organization, and the existing IDC (Start URL/Region) flow — just don't regress or hang on any of kiro-cli's current menu options.

## Decisions

**Generalize the PTY prompt loop into an ordered list of (matcher, answer) rules instead of two hardcoded `if` blocks.** Today's loop hardcodes exactly two sequential prompts. Adding a third (the login-method menu) as another special-cased `if` works but doesn't scale if kiro-cli's prompt sequence changes again. Represent known prompts as an ordered list of `(regex_or_substring, answer_bytes_or_callable)` tried against newly-arrived text, each firing at most once, so a future prompt only needs a new list entry. Alternative considered: keep hardcoding as a third `if` block — rejected only because we're already touching this loop and the list form is barely more code; not worth a bigger refactor than that.

**Answer the login-method menu by sending a bare `\n` (accept the pre-highlighted default, Builder ID).** kiro-cli defaults the cursor to `Use with Builder ID`; sending Enter without an arrow key accepts it. This matches the documented fallback behavior in `crew-auth` ("falls back to Builder ID (free tier) when [identity provider vars] are not [set]") and needs no new configuration surface. If `KIRO_LICENSE`/`KIRO_IDENTITY_PROVIDER` are set, we still expect the Start URL/Region prompts, not this menu — treat the menu as specifically the no-identity-provider case and answer it only when we haven't seen a Start URL prompt yet.

**Add a PTY transcript fixture test for the Builder ID menu path.** The bug wasn't caught by existing tests because `test_transport.py`'s login tests presumably mock or fixture the PTY output for the already-handled prompt sequence (verify while implementing) — there's no existing coverage for the no-identity-provider menu path. Capture the actual menu text observed live in this session as the fixture.

## Risks / Trade-offs

- [Risk] The login-method menu's exact wording/order could differ across kiro-cli versions, making a substring match brittle. → Mitigation: match on a distinctive stable substring (`"Select login method"`) rather than the full menu text or option list, and keep the matcher list structure from the first decision above so a future wording change is a one-line fix.
- [Risk] Sending a bare `\n` to accept "Builder ID" assumes it stays the pre-highlighted default across kiro-cli versions. → Mitigation: same distinctive-substring detection as above makes it easy to add explicit arrow-key navigation later if kiro-cli ever changes the default option order.

## Migration Plan

No data migration. Fix + test land in `transport/server.py` and `transport/test_transport.py`, `localhost/transport:latest` gets rebuilt on next `./install.sh`, existing `ga-transport` containers pick it up on their next reinstall/restart. No `ga-kiro-auth` format change. Rollback is reverting the commit and rebuilding.
