# Design

## Context

See proposal.md for motivation. the local instance runs locally on the the dedicated local Podman connection Podman connection at localhost:64057. The host’s default Podman connection targets a different unavailable machine. Repo config is ignored by Git; no macOS user override was present during inspection. Before the initial activation, generated Compose had `GA_CREW_AGENT=kiro`; it now has `kiro,codex`. The config resolver maps `backends.default` to the runtime backend list and the installer builds its toolchains.

A design is included because activation rebuilds the crew image and recreates local services, requiring target selection, deployment approval, and credential verification.

## Goals / Non-Goals

**Goals:** Produce a minimal local edit with verifiable backend ordering and an explicit activation procedure.

**Non-Goals:** Change shared defaults, enable Claude, change the default backend, migrate existing crews, alter the production instance, or introduce new backend semantics.

## Decisions

- Add the YAML list `[kiro, codex]` under the existing `backends` mapping. Ordering preserves Kiro as default. Keep the Kiro identity center URL, region, Sonnet override, and 10800-second timeout unchanged. Do not set a global model override or invent a Codex model pin.
- Edit the source YAML rather than generated Compose, which the next install overwrites. Do not force-add the ignored operator config to Git; the tracked artifacts document the intended local state.
- Use the existing resolver to check the effective config and `GA_CREW_AGENT=kiro,codex` without installing. Explicit `--config` on install avoids an unrelated user override changing this rollout.
- Build Codex into the crew image through the supported installer. Existing crew containers retain their original image and backend; verify with a new disposable crew after approval.
- Inspect credential status without reading secret contents. If Codex needs login, use The local instance’s existing auth flow and let the operator complete interactive authentication; credentials never enter YAML or planning artifacts.

### Codex integration repairs

The first ChatGPT login attempts timed out after 45 seconds. Transport logs showed `spawn codex ENOENT`: codex-acp 1.12.0 starts `codex app-server`, but the image exposed only `codex-acp`. Its bundled `@openai/codex` dependency already provided CLI 0.154.0 under npm’s nested dependency directory.

- Expose that exact dependency with a build-time `/usr/local/bin/codex` symlink to `$(npm root -g)/@agentclientprotocol/codex-acp/node_modules/.bin/codex`. Run `codex --version` during the image build to fail early if the dependency layout changes. This preserves adapter/CLI compatibility without a second package pin or global model change.
- Use `codex login --device-auth` for the existing ChatGPT method. `codex-acp` is an ACP stdio server, not a standalone login CLI. Keep the existing ephemeral-container, PTY, credential capture, and profile persistence machinery.
- Update login command assertions and lifecycle documentation. Verify both the focused test suite and a disposable-container device-auth URL probe. Account authorization still requires the operator and is separate from confirming URL generation.
- The live endpoint now returns HTTP 200 with the device URL, but `code` is null. Codex CLI 0.154.0 prints “Enter this one-time code (expires in 15 minutes)” and then the ANSI-colored code on a separate line. Update extraction to handle that exact output, including formatting and expiry text, and add a representative parser regression test. Do not treat a generic device URL without its required code as a complete login handoff.
- The observed timeout is a symptom of the executable/command defects, so increasing the deadline or changing account security settings is not the repair.

### Codex sandbox compatibility

After successful device authentication, the first Codex task failed before model execution with `AcpToolGateUnroutable`. Ghostship forced `sandbox: off` and allowed unsandboxed fallback for all backends. Codex's enforced permission route requires KiroCrew's OS credential mask. Use `sandbox: auto` and `sandbox_allow_unsandboxed_exec: false` for Codex crews only. Preserve existing settings for other backends. A disposable image probe with the crew's no-new-privileges and capability drops detects a namespace backend and confirms the mask applies. Never bypass or downgrade the permission-route check.

### Signing-key seal compatibility

KiroCrew’s namespace detector succeeds but its legacy remount of a mode-000 signing-key stand-in fails EACCES, reproduced with a dummy key in a disposable container. Patch only the exact upstream block during spec-ops image build: open the mounted stand-in with O_PATH and apply MOUNT_ATTR_RDONLY using mount_setattr with AT_EMPTY_PATH. This preserves all existing mount flags and does not change the key mask to readable data. The patch supports the deployed x86_64/aarch64 Linux syscall ABI and refuses unsupported architectures or syscall failures. Source mismatch fails the image build for review. Remove the compatibility patch once the pinned upstream image includes a verified equivalent fix.

The disposable integration probe requires reads, writes, and chmod of the masked file to fail while the original dummy key remains unchanged. Do not disable the mask, run Codex unsandboxed, or loosen container privilege restrictions.

## Risks / Trade-offs

- [Wrong Podman target] → Verify the named the dedicated local Podman connection connection and installer target before execution; avoid changing the global default connection.
- [Reinstall interrupts local transport access] → Obtain explicit manual-versus-CI/CD deployment confirmation and arrange a short local interruption; build duration is variable.
- [Credentials absent or expired] → Report authentication as pending and request operator completion; distinguish backend enabled from authenticated smoke test success.
- [Ignored config cannot be reproduced from Git alone] → Keep the exact intended edit and verification criteria in this pylon.
- [Old specs use retired backend environment names] → Follow the current YAML example and resolver for this backend activation and integration repair; avoid expanding scope into historical spec cleanup.

## Migration Plan

1. Capture the pre-edit non-secret config and backend list; inventory existing crews read-only.
2. Apply the local YAML edit and verify resolved ordering and preserved settings without installing.
3. Present `./bin/install.sh --config config/ghostship.yaml` from this repository, confirm its local Podman targeting, and ask whether to deploy manually or via CI/CD. Execute only after explicit deployment approval. Preserve current API-key handling and do not pass credential values on the command line.
4. Rebuild the crew and transport images with the CLI-path and login-command fixes after explicit approval; verify `codex --version` and device URL generation, then verify generated and running `GA_CREW_AGENT=kiro,codex`, healthy local services, and Codex toolchain presence in the rebuilt crew image.
5. Check The local instance’s Codex credential status. After any necessary operator login, launch a new disposable Codex crew and run a trivial read-only task. Verify default backend remains Kiro using configuration and a default-backend launch. Record results and any auth blocker. Remove only disposable crews with the required cleanup confirmation.
6. If rollback is needed, restore the prior backend list and, with deployment approval, reinstall against the same local instance. Do not delete credentials or existing crews as part of rollback.

## Verification evidence

The corrected disposable-container login emitted the OpenAI device authentication URL. All 92 tests in `tests/unit/test_login.py` passed and `git diff --check` passed. User approved installation of these fixes. Runtime service readiness and completion of operator login must be verified independently; do not infer them from a successful image build. See verification.md for installation observations.
