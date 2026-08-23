## 1. Configuration docs gap-fill

- [x] 1.1 Add `GA_MIN_FREE_MEM_GB`, `GA_MEMORY_WAIT_SECS`, `GA_SPAWN_MIN_MEMORY_GB` to `docs/configuration.md` table, each annotated "planned — not yet in this release" (see design.md decision 3)
- [x] 1.2 Add a note in `docs/configuration.md` explaining `CREW_GATEWAY_PORT` is a hardcoded internal constant (port 5476), not user-settable via env
- [x] 1.3 Verify `CREW_GATEWAY_PORT` and `GA_FILE_SECRET` presence/accuracy in existing table; add or correct entries as needed

## 2. Auth docs coherence review

- [x] 2.1 Read `docs/auth.md` end-to-end and verify the admiral mail signing, policy signing, and API key sections form a coherent narrative
- [x] 2.2 Verify the `admiral_secret` threat model section is accurate against current `transport/server.py` behaviour
- [x] 2.3 Patch any stale cross-references or contradictions found in `docs/auth.md`

## 3. Troubleshooting doc expansion

- [x] 3.1 Add a "Crew launch failures" section to `docs/troubleshooting.md` covering common container startup errors (image not found, socket not reachable, cookie mint failure)
- [x] 3.2 Add an OOM / memory-pressure section explaining the planned `GA_MIN_FREE_MEM_GB` guard (stub, referencing TRN-19 as not yet shipped) and workarounds for current users
- [x] 3.3 Add a placeholder entry for the `_bootstrap.p` crash (TRN-16) noting it will be expanded once that fix is applied

## 4. Create docs/remote.md

- [x] 4.1 Create `docs/remote.md` with: prerequisites (Linux host, Podman, port exposure), install steps with `--api-key` and public URL flags, TLS termination via reverse proxy, MCP client registration for a remote host
- [x] 4.2 Document known limitations of remote deployment (single-host only, no HA, file-transfer port HMAC-only, no TLS on file-transfer port natively)
- [x] 4.3 Add a link to `docs/remote.md` from the relevant section in `README.md` (the "Connecting to a harness" gap noted in the proposal)

## 5. README tools table audit

- [x] 5.1 Count tools in the current README table; reconcile against proposal's "11 tools" reference — if a tool is missing, add it; if the count was wrong, note the correction
- [x] 5.2 Verify each tool description is accurate against `transport/server.py` tool definitions

## 6. Agents and architecture review

- [x] 6.1 Read `docs/agents.md` and verify persona descriptions match current agent JSONs under `academy/agents/` (check Raven lean description, Ghost/Banshee tool grants)
- [x] 6.2 Skim `docs/architecture.md` for stale section references or workarounds noted as temporary that are now fixed through TRN-1–TRN-21
- [x] 6.3 Verify the operator governance section (TRN-18) and linger section (TRN-3) in `docs/architecture.md` are accurate

## 7. STANDING_ORDERS verification

- [x] 7.1 Read `academy/steering/STANDING_ORDERS.md` and verify Maildir conventions, `verify-admiral-sig` usage, and `ghostship-mail` skill references are current
- [x] 7.2 Verify captain mailbox source convention is accurate
- [x] 7.3 Verify bounded-loop examples are correct and consistent with crew runtime behaviour
