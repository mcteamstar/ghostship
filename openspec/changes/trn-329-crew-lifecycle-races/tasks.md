# Tasks

## 1. Serialize idle stop and wake

- [ ] 1.1 Add per-crew coordination shared by the idle monitor and crew wake path; re-check activity after acquiring it and keep the registry lock released during Podman calls. Verify a barrier-based stop-versus-wake regression test leaves the crew running after a successful wake.
- [ ] 1.2 Add a case where activity advances before the reaper claims a stop. Verify the monitor skips the stop and the test passes in `tests/unit/test_monitors.py`.

## 2. Release waiters on every leader failure

- [ ] 2.1 Move restart-leader outcome publication and event signaling around the full leader path, including the initial probe and early stop. Verify injected probe and stop failures wake waiters promptly with the leader error.
- [ ] 2.2 Run the focused restart and lifecycle regression tests in `tests/unit/test_tools.py` and `tests/unit/test_lifecycle.py`; verify existing generation-stability and successful-wake cases still pass.
