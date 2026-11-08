# Tasks

## 1. Local configuration

- [x] 1.1 Recheck The local instance’s source config, user override presence, and local Podman connection; record non-secret before-state and confirm localhost:64057 targets the dedicated local Podman connection.
- [x] 1.2 Add `backends.default: [kiro, codex]` to local `config/ghostship.yaml`; use the existing YAML resolver without installing to verify `GA_CREW_AGENT=kiro,codex` and preservation of Kiro identity, region, model override, and 10800-second timeout. Record the result in this change; keep ignored config untracked.

## 2. Approved activation and runtime verification

- [x] 2.1 Prepare the local reinstall command from design.md, check installer targeting and current API-key preservation, and obtain explicit manual-versus-CI/CD deployment confirmation; verify approval and anticipated local interruption are recorded before execution.
- [x] 2.2 After approval, reinstall the local instance with the edited config; verify generated and running backend list is `kiro,codex`, the rebuilt crew image includes Codex tooling, and transport, portal, and radar are healthy on the dedicated local Podman connection.
- [x] 2.3 Check Codex auth status without exposing secrets and have the operator complete login if needed; launch a new disposable Codex crew and run a trivial read-only task, verifying its recorded backend and successful result. Keep this task pending if authentication prevents completion.
- [x] 2.4 Verify a default-backend launch still records Kiro and existing crews retain their backend; record smoke-test evidence and remove only disposable crews after required cleanup confirmation.

## 3. Codex login integration repairs discovered during activation

- [x] 3.1 Diagnose the 45-second login timeout using transport logs and image inspection; confirm `spawn codex ENOENT`, a nested compatible CLI dependency, and missing global `codex` executable.
- [x] 3.2 Expose the bundled CLI on PATH in the Codex toolchain and add a build-time version check; verify the built image runs `codex --version` as its default non-root user.
- [x] 3.3 Change the transport ChatGPT login command to `codex login --device-auth` and correct lifecycle documentation and unit expectations; verify all 92 login unit tests pass and diff whitespace checks pass.
- [x] 3.4 Reproduce URL generation with the CLI-path fix in a disposable container; verify the official OpenAI device auth URL appears without completing account authorization or persisting credentials.
- [x] 3.5 Install the fixes after explicit approval (received: “install it”); verify healthy transport/portal/radar and the live transport login endpoint returns a device URL instead of the previous HTTP 500 timeout. Record results; keep operator authentication and crew smoke tests tracked by 2.3 and 2.4.

- [x] 3.6 Fix extraction of the one-time code from Codex CLI’s multiline ANSI-colored device-login output; add a regression test using representative output with an expiry notice, verify both URL and code are returned, and deploy with approval before completing operator authentication in 2.3.

- [x] 3.7 Correct Codex crew sandbox overrides to `auto` with unsandboxed fallback disabled; verify namespace backend and credential mask availability under crew-equivalent restrictions and 159 lifecycle/login unit tests.
- [x] 3.8 Install sandbox correction under the approved the local instance repair rollout and verify a Codex smoke task completes without bypassing the enforced credential mask.

- [x] 3.9 Reproduce KiroCrew signing-key sealing EACCES with a disposable dummy key and add a checked image compatibility patch using descriptor-based mount_setattr; verify masked reads, writes, chmod denial and unchanged original key, plus patch drift refusal tests.
- [x] 3.10 Verify the rebuilt image passes the reusable sandbox isolation integration probe and completes a fresh Codex smoke task; retain fail-closed behavior and document removal of the compatibility patch when upstream is fixed.

### Completion notes

Default-backend launch is verified as Kiro and existing crew backend selections remain unchanged. A Kiro reply test reached the provider but failed because the account has exhausted its monthly usage allowance; retries will not help. The user explicitly approved deletion of the four disposable smoke crews. All four were removed through the local instance and fleet inspection confirms no TRN-312 smoke crews remain. Other crews are preserved.

## Workflow follow-up

- Archive the pylon after implementation and approved runtime verification are complete.
