# Design

## Context

`scripts/run.sh --integration` runs six shell tests but not the four Python files in `tests/integration`. Two Python suites use in-memory/fake Podman clients; the model-default and Codex-sandbox scripts need a built crew image and a Podman connection. The signature verifier is a crew-image script that reads a fixed mounted public-key path. Maildir count behavior already has unit coverage in `tests/unit/test_captain.py`.

## Goals / Non-Goals

**Goals:**
- Put each Python integration suite on a supported, repeatable runner and CI path.
- Test the real signature verifier without adding a production-only test hook or weakening its fixed key path.
- Add a disposable install/start/readiness check that cannot modify an operator's existing installation.

**Non-Goals:**
- Re-test Maildir counting behavior already covered by unit tests.
- Replace the unit suite or current shell install tests.
- Run provider-authenticated agent dispatches in CI.

## Decisions

- Run `test_profile_launch_flow.py` and `test_on_demand_recovery.py` with the normal Python integration job; both isolate Podman through mocks/fakes. Install the same declared transport requirements used by the unit job.
- Run `test_model_defaults.py` and `test_codex_sandbox.py` in a separate Podman-backed job that builds/selects the required image and uses a disposable container and dummy credentials. Make that job a release gate rather than silently skipping it when a connection is unavailable.
- Exercise `verify-admiral-sig` inside a disposable crew-image container. Mount a generated test public key at its real fixed secret path for valid and tampered-message cases; omit the secret for the missing-key exit-code case. This tests the shipped script and its runtime dependency directly.
- Run the full install/start smoke test on a clean Linux CI worker with a temporary HOME/data directory and isolated Podman resources. Verify readiness only through the portal URL, then tear down resources created by the test in a `finally` path. Keep it in its own job so setup cost and failures are visible.
- Do not change `test_captain.py` Maildir cases except as needed to retain the existing coverage.

## Risks / Trade-offs

- [Risk] Podman image builds and service startup lengthen CI → Isolate them in a dedicated job with clear timeouts and cache only immutable/pinned build inputs.
- [Risk] A failed smoke test could leave containers or volumes behind → Use unique project/resource names, a temporary home/data root, and unconditional teardown limited to those names.
- [Risk] A macOS Podman VM is not required for the Linux behavior under test → Run the smoke job on Linux and retain separate macOS-specific coverage only for machine-specific behavior.
