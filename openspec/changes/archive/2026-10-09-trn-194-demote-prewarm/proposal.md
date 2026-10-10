# Proposal: Demote prewarm from MCP tool to internal function

## Why

The `prewarm` MCP tool and `POST /crews/{crew_id}/prewarm` REST route added in TRN-131 are dead code — no skill, Captain prompt, persona steering, or external caller uses them. The tool is shown to every MCP client, adding noise to the schema for zero benefit. Warming happens automatically at launch; making it implicit in `supply` and `schedule` is a better trigger point with no user-facing cost.

## What Changes

- **BREAKING** Remove the `prewarm` MCP tool from the server's tool schema
- **BREAKING** Remove `POST /crews/{crew_id}/prewarm` REST route and handler
- Remove auth special-casing for the prewarm route in `transport/auth.py`
- Remove the public `prewarm()` wrapper in `transport/lifecycle.py`
- Keep `_prewarm_crew` as an internal helper (unchanged behaviour, unchanged gates)
- Add background prewarm trigger to `supply` (after presign, non-blocking, non-fatal)
- Add background prewarm trigger to `schedule` create path (after registry write, non-blocking, non-fatal)
- Fix CHANGELOG.md TRN-131 entry: "no-op canary dispatch" → `GET /api/ready`
- Update `docs/configuration.md` and `config/ghostship.conf.example` to remove tool documentation

## Capabilities

**Modified Capabilities:**
- `acp-prewarm` — prewarm operation changes from explicit MCP/REST surface to implicit background trigger from `supply` and `schedule`

## Impact

- `transport/server.py` — remove tool + REST handler + route entries; add `_bg_prewarm` helper; wire into `supply` and `schedule`
- `transport/lifecycle.py` — remove public `prewarm()` wrapper
- `transport/auth.py` — remove two prewarm route short-circuits
- `tests/unit/test_prewarm.py` — remove `TestPrewarmHandler` and `TestPrewarmMiddleware`; add `TestPrewarmImplicitTriggers`
- `CHANGELOG.md`, `docs/configuration.md`, `config/ghostship.conf.example` — doc cleanup
- GitHub issue #23
