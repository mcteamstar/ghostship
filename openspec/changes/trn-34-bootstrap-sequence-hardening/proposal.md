## Why

`_finish_crew_setup` bootstraps a new crew container, but its step ordering is not principled — steps are sequenced by when they were added, not by their actual dependencies. This produced a real race condition: the admiral signing secret (auth material for Raven) is injected after agents and skills are copied, well after the gateway is live for the second time. A concurrent Raven dispatch at that moment gets a signature verification failure. Additionally, the secret write lacks `os.fsync`, leaving a kernel-buffer window where a near-simultaneous read returns empty.

## What Changes

- Move `admiral_secret` generation and injection to immediately after `_inject_auth`, before `_patch_crew_config` and the container restart — so the secret is in place before the gateway ever starts its second life
- Add `os.fsync(fd)` to the secret injection script before `os.close(fd)` to ensure the write is durable before any process can read the file
- Move `_inject_policy` to after `_seed_openspec_store` (it depends only on `admiral_secret`, not on the post-restart gateway)
- Document the dependency rationale for each step in `_finish_crew_setup` with inline comments so the ordering is not accidentally broken in future

No other functional changes. The correct order is documented in the ticket and in the design.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `crew-lifecycle`: `_finish_crew_setup` step ordering is corrected; `admiral_secret` injection gains `os.fsync`

## Impact

- `transport/server.py` — `_finish_crew_setup` only; ~20 lines moved, 1 line added (`os.fsync`)
- `transport/test_transport.py` — add a test asserting the admiral secret is present before the post-restart gateway wait completes
