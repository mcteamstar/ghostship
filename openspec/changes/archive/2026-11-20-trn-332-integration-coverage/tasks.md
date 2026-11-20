# Tasks

## 1. Include lightweight Python integration suites

- [x] 1.1 Add `test_profile_launch_flow.py` and `test_on_demand_recovery.py` to the supported integration runner and CI job. Verify `scripts/run.sh --integration` executes both and fails when either suite fails.
- [x] 1.2 Document the supported integration command and dependencies in the contributor/release verification docs. Verify each documented command matches the CI invocation.

## 2. Add Podman-backed behavioral coverage

- [x] 2.1 Add a dedicated Podman-backed CI job that builds/selects the required crew image and runs `test_model_defaults.py` and `test_codex_sandbox.py` in disposable containers. Verify missing image/connection or test failure fails the job rather than silently skipping it.
- [x] 2.2 Add `verify-admiral-sig` behavioral tests in a disposable crew-image container using a generated Ed25519 key and the real mounted-key path. Verify exit codes 0 for valid, 1 for tampered and malformed messages, and 2 for a missing key without changing production key-path behavior.

## 3. Exercise a fresh install and startup

- [x] 3.1 Add a Linux Podman smoke job using a temporary HOME/data directory and unique resource names; install, start, and verify `/health` through the portal endpoint. Verify portal-to-transport failures make the job fail.
- [x] 3.2 Add unconditional cleanup for only the smoke job's resources and document the release verification entry point. Verify cleanup runs on both successful readiness and forced failure paths.
