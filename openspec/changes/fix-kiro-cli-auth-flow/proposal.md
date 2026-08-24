## Why

A fresh end-to-end test (`./install.sh` with no flags, then `launch` + `dispatch`) originally surfaced two auth bugs. One is already fixed on `main` (`febeb6e`'s orientation/graduation image restructure, which restores `USER kirocrew` on the crew image — confirmed live in this session: a crew launched post-login now dispatches successfully on the first attempt). The other is still live: `POST /login` times out and returns HTTP 500 for any install that hasn't configured an org identity provider — i.e. the default/free-tier Builder ID path — because `kiro-cli` now shows an interactive login-method selection menu that the PTY-answering handler doesn't recognize, so it never gets past the 15s timeout to produce a device code.

## What Changes

- Fix `POST /login`'s PTY-answering logic (`transport/server.py`, `_handle_login_post`) to detect and answer the `Select login method` menu that `kiro-cli login --use-device-flow` shows when no identity provider is configured, so the Builder ID (free tier) login path actually completes instead of timing out at 15s.
- Add a PTY transcript fixture test covering the Builder ID menu path, so this stays fixed.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `crew-login`: `POST /login`'s PTY prompt-answering behavior must also handle the `Select login method` menu (Builder ID / Google / GitHub / Your Organization) that appears when no identity provider is configured, not just the `Start URL`/`Region` prompts used by the IAM Identity Center path.
- `crew-auth`: the "Identity provider configuration" requirement's "No identity provider configured" scenario needs to reflect the interactive menu step kiro-cli now shows before the device code appears.

## Impact

- `transport/server.py`: `_handle_login_post` (PTY prompt-answering loop, ~line 2479-2560).
- `transport/test_transport.py`: new test for the login PTY menu handling.
- No changes to `install.sh`/`uninstall.sh`, `_inject_auth`, or the crew images — this is purely the login PTY handler.
- Affects every fresh install that doesn't configure an org identity provider: Builder ID/free-tier logins can't complete at all today.
