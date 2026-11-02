# TRN-293 — Design

## Overview

Bump the Ghostship spec-ops crew image from KiroCrew v0.10.0 to v0.11.1.
This is a base-image pin update with a mandatory seed verification step.
No changes to transport, academy, agents, steering, or install scripts.

## Key motivations (from research)

1. **Memory WAL fix** — concurrent memory reads no longer block behind writes;
   WAL is preserved when another process closes the DB. Critical for the
   7-concurrent-reviewer independent-review template.
2. **Shell reader security fix** — closes a bypass where `bash -c 'cmd'` placed
   after options/redirections was not caught by the deny-list parser.
3. **Three CVEs resolved** — filelock (GHSA-v4x8-3wr5-3wq8), undici
   (GHSA-4w7w-5xrc-9h26), zod (GHSA-mrhx-c7xc-m3w5).

## What does NOT change

- `GA_CREW_AGENT` remains `kiro` — KAS engine is not adopted in this TRN
- Academy agents, steering, orders — unchanged
- Transport — unchanged
- Install scripts — unchanged
- KAS binary: operators who don't want it should pass `--no-kas` to `./install.sh`
  (new upstream default; Ghostship install.sh passes `--no-kas` if it detects an
  existing `GA_CREW_AGENT=kiro` config)

## Files changed

| File | Change |
|:-----|:-------|
| `crews/_base/admission/Containerfile` | Bump `KC_BASE_IMAGE` default to v0.11.1 digest |
| `crews/_base/graduation/seed_kiro_db.py` | Update migration rows if schema changed; update verification annotation |

## Step-by-step

### D1 — Get v0.11.1 digest

On a host with podman available (corsair or starport):
```bash
podman manifest inspect ghcr.io/kirodotdev/kirocrew:v0.11.1
```
Extract the multi-arch index digest (top-level `digest` field). This is the
immutable reference that goes into `KC_BASE_IMAGE`.

### D2 — Verify migration schema

```bash
podman run --rm ghcr.io/kirodotdev/kirocrew:v0.11.1 python3 -c \
  "import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); \
  print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
```

Expected baseline from v0.10.0: `(6, 5)`.

- If result is `(6, 5)`: update only the verification annotation in `seed_kiro_db.py`
- If result differs: update migration rows and table-creation statements accordingly

### D3 — Bump Containerfile

In `crews/_base/admission/Containerfile`:
```dockerfile
ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew@sha256:<v0.11.1-digest>
```
Update the comment block above the ARG to record:
- KiroCrew version: v0.11.1
- Digest: `sha256:<digest>`
- Verified: `<date>`

### D4 — Build and test

```bash
ghostship upgrade  # rebuilds spec-ops image
```

On corsair:
- `curl -s http://localhost:64057/version` → transport version (not crew image)
- Launch a test crew: `corsair_launch(crew_id="trn-293-test")`
- Dispatch a trivial Ghost task and confirm it completes
- `corsair_nuke(crew_id="trn-293-test", confirm=True)`

On carrier: same steps via carrier_launch/pickup/nuke.

### D5 — e2e

```bash
scripts/run.sh --e2e  # 23 passed expected
```

### D6 — Commit, push, PR → main, tag

Commit on `release/0.11.0`, PR to main, merge squash, tag `v0.11.0`.
Update adjutant submodule and deploy starport.

## KAS engine note (out of scope)

KAS is the new upstream default for fresh installs. Ghostship pins `GA_CREW_AGENT=kiro`
and is unaffected. A future TRN should evaluate migrating workers to KAS — this would
require mapping `deniedCommands`/`allowedCommands` in agent JSONs to KAS spec
`permissions` format.
