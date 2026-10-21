# Tasks

## 1. Transport

- [x] 1.1 In `_crew_api_with_recovery` (`transport/lifecycle.py`), keep the last `httpx.HTTPStatusError` across phases and, at every point that raises `CrewUnresponsiveError` after an HTTP error, append `Last gateway response: HTTP <status>: <body>` (body redacted and truncated to 500 characters), and when that status is 4xx replace the trailing "Suggestion: check crew status …" with "the crew gateway rejected the request; see the response above" (design Decision 1). Recovery logic is unchanged. Verify: a unit test with a fake gateway that always returns `400 {"error": "Agent 'ghost' not found"}` asserts the raised message contains "unresponsive", "HTTP 400", "Agent 'ghost' not found" and the rejected-request suggestion, and no longer the "check crew status" one; a second asserts a body containing the cookie value comes back redacted and at most 500 characters long; existing recovery tests still pass.
- [x] 1.2 In `AcademyLoader._stage_skills` (`transport/academy.py`), skip `__pycache__/` directories and `*.pyc` files (design Decision 2). Verify: a unit test with a skill holding `SKILL.md`, `scripts/x` and `scripts/__pycache__/x.cpython-313.pyc` produces tar members `SKILL.md` and `scripts/x` only.

## 2. CLI and install

- [x] 2.1 In the `ghostship` CLI status and `bin/install.sh` post-install CA output, inspect `ga_ga-portal-data` first, then `ga-portal-data` (design Decision 3). Verify: a unit test of the CLI lookup with a stubbed `podman volume inspect` that succeeds only for `ga_ga-portal-data` reports the CA path; on the live install, `ghostship status` prints the CA cert path, not "ga-portal-data volume not found".

## 3. Academy

- [x] 3.1 Add the "change artifacts describe target behaviour, not your current instructions" paragraph to `academy/orders/spec-driven-development.md` and `academy/orders/independent-review.md` (design Decision 5). Verify: `tests/unit/test_raven_prompt_contract.py` gains an assertion that each resolved template contains the paragraph, and it passes.

## 4. Tests and housekeeping

- [x] 4.1 `tests/e2e/helpers.py`: resolve the macOS Podman socket at runtime per design Decision 4, keeping the `GHOSTSHIP_PODMAN_SOCKET` override. Update the kiro-auth test's skip reason in `tests/e2e/test_transport_e2e.py` so it no longer says logout clears every crew's kiro-cli identity. Verify: on macOS, `scripts/run.sh --e2e` runs the stop/restart test, so it no longer appears among the skips.
- [x] 4.2 Compare `openspec/changes/trn-265-openspec-1140-upgrade/` with `openspec/changes/archive/2026-10-20-trn-265-openspec-1140-upgrade/` (their `tasks.md` differ). Copy anything the archive is missing into the archived copy, then delete the active folder. Verify: the archived `tasks.md` is the more complete one, and `openspec list` no longer shows TRN-265.
- [x] 4.3 Add a CHANGELOG v0.8.1 "Fixed" entry covering the error detail, the status CA path and the skill bytecode filter. Verify: the entry is present.
- [x] 4.4 Run the full unit suite. Verify: `scripts/run.sh --unit` exits 0.
