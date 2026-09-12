# TRN-149 Tasks: KiroCrew 0.6.0 Upgrade

## Pre-flight

- [x] **T0: Verify image availability**
  Pull `ghcr.io/kirodotdev/kirocrew:0.6.0` on the target host and confirm the
  pull succeeds. If the image is not yet published, do not proceed with the
  version bump.
  ```bash
  podman pull ghcr.io/kirodotdev/kirocrew:0.6.0
  podman inspect ghcr.io/kirodotdev/kirocrew:0.6.0 --format '{{index .Labels "org.ghostship.version"}}'
  ```

## Code changes

- [x] **T1: Bump `kc_base_image` default in `transport/config.py`**
  Change both occurrences of `ghcr.io/kirodotdev/kirocrew:0.5.0` to
  `ghcr.io/kirodotdev/kirocrew:0.6.0`:
  - `Config` dataclass field: `kc_base_image: str = "ghcr.io/kirodotdev/kirocrew:0.6.0"`
  - `from_env()` fallback: `os.environ.get("KC_BASE_IMAGE", "ghcr.io/kirodotdev/kirocrew:0.6.0")`

  Grep to confirm no other 0.5.0 version literals remain:
  ```bash
  grep -r "kirocrew:0.5.0" transport/
  ```

- [x] **T2: Update sandbox comment in `transport/lifecycle.py` (`_patch_crew_config`)**
  Replace the comment block that says "What changed in 0.5.0 is that
  sandbox='auto' (the default) now issues a MS_REMOUNT..." with the updated
  version described in design D2a. The patch value `"sandbox": "off"` itself
  does NOT change.

- [x] **T3: Update `subagent_max_turns` UI cap comment in `transport/lifecycle.py`**
  In the comment above `agent_overrides`, update "(UI cap 200)" to
  "(UI cap 1000, raised in KiroCrew 0.6.0)".

- [x] **T4: Update login container watchdog comment in `transport/lifecycle.py`**
  In `_start_login_container`, replace "be killed by the 0.5.0 loop watchdog
  after ~35s" with "the loop watchdog will recycle it after a timeout" as
  described in design D2c.

## Test and verify

- [x] **T5: Run transport unit tests**
  ```bash
  cd /home/kirocrew/workplace/kirocrew-workspace/repo
  python -m pytest transport/tests/ -x -q 2>&1 | tail -20
  ```
  All tests must pass. If any test asserts the old image tag string, update
  the assertion to `0.6.0`.

- [x] **T6: Grep for any remaining `0.5.0` version references in transport/**
  ```bash
  grep -rn "0\.5\.0" transport/ --include="*.py"
  ```
  Expected: zero results (all intentional references have been updated).
  If any remain, assess whether they are version-agnostic comments or stale
  references and fix accordingly.

## Commit

- [x] **T7: Commit**
  Stage and commit all changed files with message:
  ```
  feat(transport): bump kc_base_image to kirocrew:0.6.0 (TRN-149)

  - transport/config.py: bump KC_BASE_IMAGE default 0.5.0 → 0.6.0
  - transport/lifecycle.py: update sandbox, max_turns, and login container
    comments to reflect 0.6.0 behaviour
  - openspec: add delta spec and change artifacts for TRN-149
  ```

## Post-deploy

- [ ] **T8: Smoke test against new image**
  After deploying, launch a crew and confirm a task dispatches successfully:
  1. `launch(crew_id="smoke-test")`
  2. `dispatch(task="echo hello", agent="ghost", crew_id="smoke-test")`
  3. `pickup(task_id=..., crew_id="smoke-test", timeout_secs=60)`
  Confirm `outcome: "success"` and no `AcpRuntimeDead` in the result.

- [ ] **T9: Verify sandbox patch is present in deployed crew config**
  ```bash
  podman exec gs-<crew_id> cat /home/kirocrew/.kiro/crew/config.local.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent',{}).get('sandbox'))"
  ```
  Expected output: `off`
