# Design: secret-handling-hardening

## Context

See proposal.md for motivation. Current state relevant to approach:

**Model API keys (plaintext in compose.yml)**
`install.sh` writes `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY`
directly into the `environment:` block of the generated `compose.yml`
(lines ~775, ~778). The file is mode 600, but the values are visible in
`docker inspect`, process environment dumps, and any backup of DATA_DIR.
`server.py` reads them via `cfg.ga_crew_anthropic_api_key` / `cfg.ga_crew_openai_api_key`
after `Config.from_env()` pulls them from `os.environ`.

**KIRO_API_KEY — documented but not wired**
`ghostship.conf.example` documents `KIRO_API_KEY` and `auth.md` describes the
headless path, but `install.sh` never creates a Podman secret for it. The
variable reaches `ga-transport` only if the operator puts it in the environment
block manually. `server.py` already reads it from `os.environ.get("KIRO_API_KEY", "")`
and injects it into crew containers; the delivery gap is entirely in `install.sh`.

**Existing secret pattern**
`ga-api-key` and `ga-transport-secret` are already handled correctly: created by
`install.sh` via `podman secret create`, declared in `compose.yml`'s `secrets:`
top-level block, listed under each service's `secrets:` key, and loaded at
`/run/secrets/<name>` inside the container. `server.py` reads `ga-api-key` via a
helper that opens `/run/secrets/ga-api-key`. This is the model to extend.

**Policy HMAC and socket (design-level notes)**
The policy HMAC key is readable by the agent it governs (same UID). Documented as
accepted residual risk in `auth.md:370`. The Podman socket is mounted with
`label=disable`, giving the transport container full container-management capability.
Neither issue has an actionable fix in this change; they are noted here to confirm
scope exclusion.

## Goals / Non-Goals

**Goals:**
- Move `GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY` delivery from
  compose.yml environment variables to Podman secrets.
- Wire `KIRO_API_KEY` through `install.sh` as a Podman secret so the headless
  auth path works without manual compose editing.
- Transport reads all three keys from `/run/secrets/` at startup (or falls back
  gracefully when a secret is absent).
- Operator UX is unchanged: keys still come from `ghostship.conf` (or CLI flags);
  delivery mechanism changes, not the input surface.
- Existing `ga-api-key` (MCP bearer) and `ga-transport-secret` (portal) patterns
  are unaffected.

**Non-Goals:**
- `/tmp` staging paths (`mktemp`-based credential chunking in `lifecycle.py`) — low
  priority, separate change.
- Policy HMAC key isolation — accepted residual risk, not in scope here.
- Podman socket allowlisting proxy — significant architectural work, separate change.
- Gateway token query-parameter and `--api-key` process-list exposure — noted in
  proposal, not actionable in this change.

## Decisions

**D1: Podman external secrets, same pattern as `ga-api-key`**

All three keys (`ga-crew-anthropic-api-key`, `ga-crew-openai-api-key`,
`ga-kiro-api-key`) follow the existing `ga-api-key` pattern:
- `install.sh` creates them with `podman secret create` when the value is non-empty.
- `compose.yml` template declares them as `external: true` in the `secrets:` block
  and lists them under `ga-transport`'s `secrets:` only.
- `server.py` reads them from `/run/secrets/` at startup, not from `os.environ`.
- The env vars (`GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_OPENAI_API_KEY`, `KIRO_API_KEY`)
  are removed from the `environment:` block of `compose.yml`.

Alternatives considered:
- `umask 077` compose file (already done) — necessary but not sufficient; env vars
  still appear in `podman inspect` and process table.
- A single bundled secret file (all keys in one JSON blob) — more complex to read
  and harder to rotate individually; rejected.
- Docker secrets (non-external) — incompatible with podman-compose external secrets
  pattern already in use; rejected.

**D2: Conditional secret inclusion (same guard as `ga-api-key`)**

A key that is not configured must not produce a dangling secret reference. For each
key, `install.sh` only adds it to the compose `secrets:` block and the service's
`secrets:` list when it was provided. `server.py` falls back to empty string when
the file is absent, preserving existing behavior: missing anthropic/openai key →
OAuth fallback; missing KIRO_API_KEY → device-code flow.

**D3: `/run/secrets/` read helper in `server.py`, not `config.py`**

`config.py`'s `Config.from_env()` currently reads the keys from env vars. Rather
than changing the dataclass, `server.py` reads the secret files after `cfg =
Config.from_env()` and overwrites the config fields, mirroring how
`_load_transport_secret()` works today. This keeps `config.py` changes minimal and
preserves the existing validation/logging flow.

Alternatively, the fields could be removed from `Config` entirely (like
`ga-transport-secret`). That would be cleaner long-term but requires touching every
call-site that reads `cfg.ga_crew_anthropic_api_key`. The overwrite-after-load
approach is lower risk for this change.

**D4: Secret names**

| Purpose | Podman secret name |
|---|---|
| Anthropic API key for crews | `ga-crew-anthropic-api-key` |
| OpenAI API key for crews | `ga-crew-openai-api-key` |
| Kiro API key | `ga-kiro-api-key` |

Names follow the existing `ga-<component>-<purpose>` convention.

## Risks / Trade-offs

- **Reinstall idempotency** → Mitigation: follow the `ga-api-key` pattern —
  `podman secret rm <name> 2>/dev/null || true` before `podman secret create`.
  This means a re-run with a new key value always wins.
- **Absent secret file at startup** → Mitigation: read helper returns `""` when
  `/run/secrets/<name>` does not exist; falls back to env var value (which will now
  be empty since it's not set in compose). Behavior is identical to today when the
  key was not configured.
- **compose.yml redeploy gap** → If an operator upgrades without re-running
  `install.sh`, their old compose.yml still has the env vars. Migration note in
  tasks covers this.
- **`config.py` env vars stay wired** → `Config.from_env()` still reads
  `GA_CREW_ANTHROPIC_API_KEY` etc. from the environment. After this change those
  env vars will be empty in the compose-generated container. Any operator who sets
  them manually outside of install.sh will still have them respected, which is
  acceptable (defense-in-depth path).

## Migration Plan

1. Re-run `install.sh --config ghostship.conf` after pulling the update. The script
   creates the new Podman secrets and rewrites `compose.yml` without the env vars.
2. Restart services: `podman-compose -f DATA_DIR/compose.yml up -d --force-recreate`.
3. Rollback: restore the previous `compose.yml` from a backup and restart. The
   Podman secrets are harmless to leave in place.

Operators who have keys in `ghostship.conf` (or passed via flags) have no manual
migration steps; re-running install.sh is sufficient.

## Open Questions

None — scope is resolved and approach matches existing patterns.
