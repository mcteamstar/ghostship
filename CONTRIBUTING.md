# Contributing to Ghostship

Before contributing, read [CONTRIBUTING.md](CONTRIBUTING.md) — it explains how
ghostship is meant to be consumed and when a fork is the right answer rather
than a PR upstream. Most customisation work belongs in your own fork, not here.

## What belongs upstream

Pull requests to this repo are welcome for things that are genuinely general:

- **Bug fixes** in the transport, install scripts, or base crew image —
  especially anything that affects correctness, security, or reliability.
  Regression tests required.
- **Transport improvements** — new MCP tools, protocol changes, performance
  fixes, anything that makes the core engine better for everyone.
- **Documentation fixes** — corrections, clarifications, missing steps.
- **New compositions or academy content** — only if they're broadly useful
  to the general ghostship user base and not tied to a specific product or
  organisation's tooling.

If you're unsure whether something is general-purpose enough, open an issue
or a draft PR to discuss before investing in the implementation.

If your fork has evolved general-purpose improvements alongside
organisation-specific content — as often happens — extract the general
parts into a separate PR rather than sending everything at once.

## PR guidelines

- Open an issue or draft PR for discussion before significant transport
  changes — a short description of what and why is enough.
- Keep PRs focused. A bug fix and a new feature are two PRs.
- All existing tests must pass (`bash scripts/run.sh --unit`). Add tests for
  new behaviour.
- Commit messages follow the conventional commit style used in this repo
  (`fix:`, `feat:`, `chore:`, `docs:`, `test:`), subject line ≤50 chars.
- For security-sensitive changes (auth, HMAC, path handling), include a note
  on what was verified and how.


## Test commands

To run the integration checks with the same Python dependencies used by CI:

    python3 -m pip install -r transport/requirements.txt
    scripts/run.sh --integration

The integration category runs the six shell install checks, then
test_profile_launch_flow.py and test_on_demand_recovery.py with pytest. Those
Python suites use fake Podman clients, so this category does not require a
running Podman service. The runner reports either Python suite as a failure and
continues to run the other suite.

The crew-image checks and the fresh install/start smoke test require Podman.
They are part of the release verification workflow described in RELEASING.md.
