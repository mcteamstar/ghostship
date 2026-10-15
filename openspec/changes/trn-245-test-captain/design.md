## Context

`transport/captain.py` exposes a set of pure-Python helper functions
(`_parse_order_front_matter`, `_substitute_placeholders`,
`_validate_captain_change_name`, `_resolve_order_template`,
`_format_captain_mail`, `_parse_sentinel_file`, `_read_sentinel_file`,
`_captain_jobs`, `_captain_checkin_job`, `_mail_count`, `_captain_order_lock`)
that currently have no unit coverage. See `proposal.md` — Why for motivation.

Two of these helpers reach outside pure computation: `_read_sentinel_file` and
`_mail_count` call into a Podman client, and `_format_captain_mail` imports
`cryptography.hazmat.primitives.asymmetric.ed25519.Ed25519PrivateKey` when a
signing secret is supplied. The existing test harness already provides the
seams needed to exercise them without real containers or a real crypto backend:
`tests/fakes.py` ships `FakePodmanClient`, `FakeArchiveResponse` and
`_build_tar_with_file`, and `tests/unit/conftest.py` installs a `cryptography`
module stub when the real package is absent.

## Goals / Non-Goals

**Goals:**
- Cover every helper named in `specs/test-captain-helpers/spec.md` with
  observable-contract assertions (one or more tests per scenario).
- Drive the Podman-backed helpers through `FakePodmanClient` only — no live
  container runtime, no network, no filesystem writes outside tmp dirs.
- Keep the test file self-contained and runnable under the existing
  `tests/unit/` conftest (which already supplies the `cryptography` stub).

**Non-Goals:**
- No change to `transport/captain.py` or any other production module.
- No coverage of captain's orchestration/IO flows (job scheduling, container
  lifecycle, mail delivery side effects) — only the pure helpers and the two
  Podman-reading helpers listed in the spec.
- No new third-party test dependency; no new fakes beyond those already in
  `tests/fakes.py`.

## Decisions

**Framework: `unittest.TestCase`, not pytest-style functions.**
The proposal specifies a unittest-based file. The surrounding suite under
`tests/unit/` runs via the shared conftest regardless of style; `unittest`
keeps the file importable and runnable standalone (`python -m unittest`) and
matches the "new unittest-based test file" wording in the proposal. Chosen over
bare pytest functions so the file does not depend on pytest fixtures beyond the
conftest-installed `cryptography` stub.

**Podman helpers via `FakePodmanClient` (scripted responses), not mocks.**
`_read_sentinel_file` is tested by scripting a sentinel tar through
`FakePodmanClient` (built with `_build_tar_with_file`) and by scripting the
archive API to raise, asserting a `None` return. `_mail_count` is tested by
scripting `container_exec_checked` return strings (`"3 2"` → 5, `"7"` → 7,
`"invalid output"` → 0). Preferred over `unittest.mock` because the fakes are
the suite's established seam and encode the real Podman API contract, so the
tests stay faithful to how captain actually calls the client.

**Signing tested against the conftest `cryptography` stub.**
`_format_captain_mail` signing tests pass a 32-byte hex seed and assert the
presence of an `X-Admiral-Sig` header rather than verifying the signature
bytes — the stub's Ed25519 output is not the real curve, so only the header's
presence and the `ValueError` on a newline-injected subject are observable
contracts. Verifying actual signature bytes would couple the test to whichever
backend (stub vs real `cryptography`) happens to be installed.

**Templates: real template from `_list_order_templates`, tmp dir fallback.**
`_resolve_order_template` success is exercised with a template name returned by
`_list_order_templates()` when `academy/orders/` yields one; the
dual-placeholder (`<change>` + `<changes>`) and `change_name=None` error paths
are driven through a temporary template directory so they do not depend on
repo content. This keeps the happy path honest while making the error paths
deterministic.

## Risks / Trade-offs

- [Signing assertions are shallow — only header presence is checked, not a real
  Ed25519 verification] → Mitigation: this is the only backend-independent
  contract; the newline-injection `ValueError` path adds a real behavioural
  assertion, and the signature algorithm itself is cryptography-library code,
  not captain's responsibility to re-test.
- [`_resolve_order_template` happy path depends on an existing template in
  `academy/orders/`] → Mitigation: the test queries `_list_order_templates()`
  and skips the happy-path assertion gracefully if none is returned, so the
  file passes in a stripped checkout; all error paths use tmp dirs and are
  unconditional.
- [`FakePodmanClient` could drift from the real client API] → Mitigation: the
  fake is already the suite-wide seam used by other captain/transport tests, so
  any drift is caught suite-wide, not just here.

## Migration Plan

Additive only. The single new file `tests/unit/test_captain.py` is added to the
suite; no production code, config, or existing test changes. Rollback is a file
deletion. No deployment steps.
