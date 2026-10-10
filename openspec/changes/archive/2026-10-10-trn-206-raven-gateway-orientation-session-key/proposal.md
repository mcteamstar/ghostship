# TRN-206: Add X-Session-Key to _RAVEN_GATEWAY_ORIENTATION

## Problem

`_RAVEN_GATEWAY_ORIENTATION` in `transport/captain.py` tells Raven to authenticate
`POST /api/spawn` calls with only `X-Internal-Secret`. This is insufficient for
attested spawns — the gateway returns `member_identity_unavailable` (HTTP 409) because
no session key is present to verify the spawning identity.

The SDD and indy templates work around this by explicitly instructing Raven to also
pass `X-Session-Key: $KIRO_SESSION_ID`. Free-form captain orders use only
`_RAVEN_GATEWAY_ORIENTATION` and don't include this instruction, so Raven cannot
spawn any personas from within them.

## Fix

Add `X-Session-Key: $KIRO_SESSION_ID` to the spawn authentication instructions in
`_RAVEN_GATEWAY_ORIENTATION` alongside the existing `X-Internal-Secret` instruction.

This makes all captain orders — not just SDD/indy templates — able to spawn personas
with attested sessions. No template changes needed.

## Scope

- `transport/captain.py` — `_RAVEN_GATEWAY_ORIENTATION` string constant (~line 53)

## Files affected

- `transport/captain.py`
