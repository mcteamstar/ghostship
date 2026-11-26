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

## Radar UI (frontend)

The Radar browser UI is a React app in `radar/web` (TypeScript, Vite, Vitest). Its Node version is pinned in `radar/web/.nvmrc` to Node 26 LTS. The `ga-radar` image compiles the app in a `node:26-alpine` build stage, so Node is only needed on a development machine.

Run these from `radar/web`:

    npm ci              # install from the committed lockfile
    npm run typecheck   # TypeScript check (CI runs this too)
    npm test            # Vitest component and hook tests (CI runs this too)
    npm run build       # bundle to radar/web/dist, the same step the image runs
    npm run dev         # Vite dev server on http://localhost:5173

The dev server proxies `/api`, `/crews` and `/dashboard` to a running portal. The default target is `http://localhost:64057`. Point it at another portal with `RADAR_PROXY_TARGET`:

    RADAR_PROXY_TARGET=https://your-portal-host npm run dev

The proxy forwards the browser's `Host` header unchanged, so Radar's same-origin check on the Refresh auth action still passes. The portal must accept that `Host` value.

The Python docs-parity tests in `tests/unit` read the React sources, so a change to the wording or wiring of Radar also runs through `bash scripts/run.sh --unit`.
