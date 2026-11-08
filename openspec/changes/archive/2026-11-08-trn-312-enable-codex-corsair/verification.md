# Verification

- The dedicated local Podman connection hosts ga-transport, ga-portal, and ga-radar; portal binds localhost:64057.
- User override absent; prior default backend list was `[kiro]`.
- Added local `backends.default: [kiro, codex]`; resolver returns `GA_CREW_AGENT=kiro,codex`.
- Deep comparison against the prior resolved config confirms this backend list is the only change. Kiro identity, region, model override, timeout, and other settings are preserved.
- Before-state config and crew inventory captured under `/tmp/trn-312-*`.
- Deployment and runtime smoke tests await explicit deployment approval.

## Activation prepared

Command from repository root: `./bin/install.sh --config config/ghostship.yaml`.
Resolved machine settings select dedicated the dedicated local Podman connection; installer uses the explicit named Podman connection on macOS. API-key resolution reuses saved configuration when present; the existing internal transport secret is retained. No secret values were read.

Local configuration remains Git-ignored. OpenSpec validation passed with the expected warning for convention-required `ticket` metadata. Tasks 1.1 and 1.2 are complete; deployment approval and runtime checks remain pending. Reinstall can briefly interrupt local transport/portal access and rebuild duration varies.

## Activation result

User requested the local update and also ran `ghostship upgrade` successfully. The install operations overlapped, producing container-name conflicts in the assistant installer log. Final independent checks: localhost:64057/health returns HTTP 200 with `ok`; running ga-transport has `GA_CREW_AGENT=kiro,codex`; spec-ops image toolchain label includes `codex`. The user’s upgrade reports successful local service startup and Kiro runtime default.

`ghostship auth status --url http://localhost:64057` lists only the Kiro identity-center default profile. Codex authentication is absent, so authenticated Codex smoke testing remains pending operator login. Tasks 2.1 and 2.2 are complete; 2.3 and 2.4 remain pending.

## Codex login troubleshooting (2026-11-08)

Other tmux pane showed two HTTP 500 login timeouts. Transport log identifies `spawn codex ENOENT` from codex-acp starting app-server. Image inspection confirms codex-acp 1.12.0 and bundled Codex CLI 0.154.0 are present, but only codex-acp is on PATH. The transport also incorrectly invokes the ACP stdio server with `login`.

Prepared source fixes: expose the bundled compatible CLI as `/usr/local/bin/codex` during image build; run `codex login --device-auth` for ChatGPT authentication; update login tests and lifecycle documentation. Disposable-container reproduction with the proposed symlink emits the official OpenAI device auth URL, without completing or persisting login. Login unit suite: 92 passed. `git diff --check` passed. No running transport patch or redeployment performed; approval required for rebuild with these additional source fixes.

## Fix installation result and remaining parser defect

Installation completed successfully. All three local services are running; independent `/health` check returned HTTP 200 `ok`. The rebuilt image runs `codex-cli 0.154.0`. Live POST `/login/codex/chatgpt` returned HTTP 200 with the official device URL, resolving the original 500 timeout. Its `code` field was null. The captured CLI output prints the code separately after an expiry notice and with ANSI color codes; current regex does not handle that layout. Recorded task 3.6 for parser correction and regression coverage. No account authorization completed.

## Parser fix completed

Codex code pattern now accepts the expiry notice and multiline code after ANSI stripping. The shared PTY reader waits for both URL and code for Codex only, avoiding early URL-only return across split chunks. Added socket-based regression tests for colored split output, required-code omission, and optional-code behavior for other flows. All 95 login tests passed. Installed under the existing local repair approval; install exited successfully, health is HTTP 200, and the live Codex ChatGPT login endpoint returned HTTP 200 with both device URL and nonempty code. Task 3.6 complete. Operator login and crew smoke tests remain pending.

## Codex execution restored

ChatGPT credential is saved. The first Codex smoke failed with AcpToolGateUnroutable because the generated config forced sandbox off; Codex now uses auto sandbox with unsandboxed fallback disabled. Namespace detection and credential-mask availability were confirmed under no-new-privileges with SYS_ADMIN/NET_RAW dropped.

A fresh crew exposed a separate upstream KiroCrew failure sealing its mode-000 signing-key stand-in (EACCES on legacy remount). Reproduced using a dummy key, independent of real credentials. The spec-ops image now applies a source-checked compatibility patch that sets read-only through mount_setattr on an O_PATH descriptor, retaining all existing restrictions. Unsupported architecture, syscall failure, or changed upstream block refuses rather than bypassing sealing.

Reusable disposable-image integration probe passed: masked reads/writes/chmod denied; original dummy key unchanged; injected sealing syscall failure prevents the child from starting. Focused lifecycle/login/patch tests: 161 passed. The corrected image and transport were installed successfully and health returned 200. Fresh Codex crew `credential-isolation smoke crew` task [task identifier omitted] completed with exact result CODEX_SMOKE_OK and no error.

The default-backend crew records Kiro; existing crew backend records remain unchanged. Kiro reply task [task identifier omitted] reached the provider but was rejected for monthly usage exhaustion, not changed backend selection. Four disposable smoke crews were retained pending explicit destruction permission; cleanup portion of task 2.4 remains open.

## Cleanup complete

User explicitly approved cleanup. the local instance nuke returned status nuked for Codex smoke crew, default-backend smoke crew, sandbox smoke crew, and credential-isolation smoke crew. Fleet inspection confirms no TRN-312 smoke crews remain; unrelated crews are preserved. Task 2.4 complete. All implementation tasks are checked; archive remains a separate workflow follow-up.
