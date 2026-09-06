## Context

See `proposal.md` for motivation. The relevant implementation sits in two files:

- `transport/server.py` — the `supply()` MCP tool function that presigns upload URLs
- `transport/files.py` — `_sign_upload_url()`, `_verify_file_token()`, and `_transfer_upload()`, which handle signing and the actual in-container bundle clone

The HMAC payload for upload tokens currently encodes `crew_id`, `path`, `expires`, the method (`POST`), and a sorted flags string containing whichever of `bundle` and `unpack` are active. Token verification in `_verify_file_token()` reconstructs that same payload and compares digests.

The bundle clone path in `_transfer_upload()` runs `git clone <staged_file> <destination>` inside the container. `git clone` fails with a non-zero exit if `<destination>` already exists and is non-empty. That failure propagates as a 500.

## Goals / Non-Goals

**Goals:**
- Add `force: bool = False` to `supply()` so callers can opt into destructive pre-clone removal
- Extend the HMAC payload to include `force` as a signed flag, preventing replay of a non-force token as a force token
- Remove the existing destination inside the container (via `rm -rf`) before the clone when `force=True` and `bundle=True`
- Leave all existing `force=False` behaviour (including the "reject occupied destination" scenario) exactly unchanged
- Add a unit test that confirms the pre-clone removal happens and the subsequent clone succeeds

**Non-Goals:**
- Force-mode for non-bundle uploads (`unpack=True` or plain file writes) — those modes don't fail on existing destinations, so no `force` semantics are needed there
- Exposing `force` through the presigned URL query string to the HTTP handler — `force` is resolved at presign time; the HTTP handler only needs to verify the token that was signed with or without `force`
- Any UI or CLI changes outside the MCP tool function signature

## Decisions

**D1 — include `force` in the signed HMAC payload, not as a separate URL query param verified at handler time.**

The existing pattern for `bundle` and `unpack` is to include them as sorted flags in the HMAC payload and separately append them as query params for the HTTP handler. We follow the same pattern for `force`. This means a token signed with `force=False` cannot be replayed to trigger a destructive pre-clone removal, matching the security intent stated in the ticket.

Alternative considered: verify `force` only at `supply()` call time and not sign it. Rejected because the presigned URL is handed to an external caller who POSTs the bundle bytes — if `force` were unsigned, a man-in-the-middle or a reused URL could trigger unintended deletion.

**D2 — execute `rm -rf <destination>` via `podman.container_exec_checked` using a list-form command (no shell interpolation).**

`_transfer_upload` already uses list-form exec calls for safety. `rm -rf` on `destination` mirrors the caller's intent (nuke the old repo checkout) and is scoped to the container's filesystem. No shell=True, no string interpolation of `destination`.

Alternative considered: rename/move the existing destination before clone, restoring on failure. Rejected as over-engineering — the caller explicitly opted in to destruction; rollback semantics add complexity for no stated need.

**D3 — `force=True` is a no-op when `bundle=False`.**

The deletion guard is only applied in the `if bundle:` branch of `_transfer_upload`. Plain file writes and tar unpacks silently ignore `force`. This keeps the surface area minimal and matches the ticket scope.

## Risks / Trade-offs

- **[Risk] Irreversible within the container** — `rm -rf` on the destination inside the container's workspace is permanent for that crew's volume. No undo path.  
  → Mitigation: the flag is opt-in (`force=False` default), the HMAC signs the intent, and the caller must explicitly pass `force=True` to `supply()`.

- **[Risk] Race between token issuance and use** — a `force=True` token signed at presign time could be used minutes later after the destination state has changed.  
  → Mitigation: presigned URLs expire in 300 seconds (existing TTL), limiting the replay window. No additional mitigation needed.

- **[Risk] `_verify_file_token` mode reconstruction must stay in sync with `_sign_upload_url`** — both functions independently reconstruct the flags string. If one adds `force` and the other doesn't, verification breaks.  
  → Mitigation: both functions are updated in the same task; the test covers the round-trip (sign then verify).

## Migration Plan

No migration needed. The change is additive: `force` defaults to `False`, existing callers are unaffected. No data model changes, no config changes, no deployment steps beyond shipping the updated transport image.

## Open Questions

None. All design decisions are resolved above.
