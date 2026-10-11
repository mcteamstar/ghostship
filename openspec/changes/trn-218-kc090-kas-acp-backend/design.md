# Design — KAS ACP backend (TRN-218)

## Context

KAS is the fourth ACP backend. Ghostship already supports:

- `kiro` — `_ALWAYS_ENABLED_BACKEND`, bundled, no toolchain, no credential.
- `claude` (TRN-202) — toolchain install + `ga-claude-auth` credential file.
- `codex` (TRN-202) — toolchain install + env-var API key.
- `opencode` (TRN-168, proposed) — toolchain install + `ga-opencode-auth`.

KAS is structurally **closest to `kiro`**: it is bundled in the KiroCrew 0.9.0
gateway image, so there is no toolchain script, no login flow, and no credential
mount. The only moving parts are the two transport-side gates that currently
reject the name, plus the config-write branch that selects the runtime.

The research report (`kc-090-research.md`, TRN-218 section) read
`transport/config.py` lines 75–83, `transport/lifecycle.py` lines 1833–1843,
and `academy/agents/*.json`. This design is grounded in those reads, re-verified
against the current source below.

## Goals / Non-Goals

**Goals:**
- Accept `kas` as a valid `GA_AGENT_BACKENDS` / `GA_CREW_ACP_BACKEND` name.
- Write `agent.acp_backend = "kas"` so the gateway routes spawns through KAS.
- Keep transport-side and shell-side validation in step.

**Non-goals:**
- A toolchain install script (KAS is bundled).
- A login flow or credential mount (KAS authenticates via the gateway runtime).
- Making KAS the default backend.
- Changing per-agent `model` fields (see Decision D3).

## Source as it stands today

### `transport/config.py` — the validation gate (line 74)

```python
_CADDY_TLS_MODES: frozenset[str] = frozenset({"internal", "tailscale", "acme", "off"})
_ACP_BACKEND_VALUES: frozenset[str] = frozenset({"kiro", "claude", "codex"})


def _validate_acp_backend(value: str) -> str:
    if value in _ACP_BACKEND_VALUES:
        return value
    raise ConfigError(
        f"GA_CREW_ACP_BACKEND={value!r} is not one of {sorted(_ACP_BACKEND_VALUES)}; "
        "must be 'kiro', 'claude', or 'codex'"
    )
```

`parse_agent_backends()` (lines 90–119) validates each name in
`GA_AGENT_BACKENDS` against the **same** frozenset:

```python
if name not in _ACP_BACKEND_VALUES:
    raise ConfigError(
        f"GA_AGENT_BACKENDS contains unknown backend {name!r}; "
        f"valid names are {sorted(_ACP_BACKEND_VALUES)}"
    )
```

Both gates read `_ACP_BACKEND_VALUES`, so adding `"kas"` to the frozenset is the
single change that unblocks both env vars. The hardcoded tail of the
`_validate_acp_backend` message (`"must be 'kiro', 'claude', or 'codex'"`) is
the only place the names are repeated literally and must be updated too.

### `transport/lifecycle.py` — the config-write branch (~1835–1843)

```python
    # When GA_CREW_ACP_BACKEND=claude, write acp_backend into the crew config so
    # the gateway routes agent spawns through the Claude Code ACP runtime rather
    # than the kiro-cli runtime.
    if GA_CREW_ACP_BACKEND == "claude":
        agent_overrides["acp_backend"] = "claude"
    # When GA_CREW_ACP_BACKEND=codex, route agent spawns through the Codex ACP
    # runtime. ...
    elif GA_CREW_ACP_BACKEND == "codex":
        agent_overrides["acp_backend"] = "codex"
```

`kiro` is deliberately absent here — the default needs no override. A `kas`
value today falls through this if/elif chain and the gateway uses `kiro`.

### `academy/agents/*.json` — model declarations

All six agents (`raven`, `ghost`, `spectre`, `banshee`, `wraith`, `reaper`)
declare `"model": "gpt-5.6-luna"`. KAS routes to a different model provider; see
Decision D3 for how this interacts with backend selection.

## Decisions

### D1: Add `"kas"` to `_ACP_BACKEND_VALUES`, not a separate set

Both validation paths already read one frozenset. A separate "bundled backends"
set would fork the validation logic for no benefit — `kiro` is already in the
shared set despite being always-enabled. Keep KAS in the same set; its
bundled-ness is expressed by the *absence* of toolchain/credential wiring, not
by a separate validation lane.

```python
# transport/config.py line 74
_ACP_BACKEND_VALUES: frozenset[str] = frozenset({"kiro", "claude", "codex", "kas"})
```

Update the message tail in `_validate_acp_backend`:

```python
    raise ConfigError(
        f"GA_CREW_ACP_BACKEND={value!r} is not one of {sorted(_ACP_BACKEND_VALUES)}; "
        "must be 'kiro', 'claude', 'codex', or 'kas'"
    )
```

`parse_agent_backends()` needs **no edit** — it already derives its valid set
and error message from `_ACP_BACKEND_VALUES`.

### D2: Add a `kas` config-write branch mirroring claude/codex

Extend the if/elif chain in `_patch_crew_config` with a `kas` branch:

```python
    if GA_CREW_ACP_BACKEND == "claude":
        agent_overrides["acp_backend"] = "claude"
    elif GA_CREW_ACP_BACKEND == "codex":
        agent_overrides["acp_backend"] = "codex"
    # When GA_CREW_ACP_BACKEND=kas, route agent spawns through the KAS (Kiro
    # Agent Service) ACP runtime bundled in the KiroCrew 0.9.0 gateway image.
    # KAS needs no credential file — it authenticates through the gateway — so
    # there is no corresponding credential-mount step at crew launch.
    elif GA_CREW_ACP_BACKEND == "kas":
        agent_overrides["acp_backend"] = "kas"
```

`agent_overrides` is deep-merged into `config.local.json` by
`patch_crew_config.py`, same as the existing branches, so no further plumbing is
needed.

### D3: Do not touch per-agent `model` fields in this change

The research report flags that all agents declare `"model": "gpt-5.6-luna"` and
that KAS routes to a different provider, so a declared model "may be ignored or
mapped incorrectly." This is a **runtime behaviour question, not a config-write
bug**, and resolving it requires observing how the 0.9.0 gateway maps a
per-agent `model` under `acp_backend=kas` — which is not knowable from the
ghostship source alone.

Decision: keep this change scoped to validation + routing. Model-mapping under
KAS is called out as an **open question** (below) and a verification task, not a
code edit. If KAS ignores the per-agent `model`, that is a follow-up ticket.

### D4: Shell parity via `agent_backends.sh`, enforced by the parity test

`scripts/lib/agent_backends.sh` applies the same rules on the install side
(noted in the `parse_agent_backends` docstring: "scripts/lib/agent_backends.sh
applies the same rules on the install side; the parity test keeps them in
step"). Add `kas` to the shell's valid set so install-time validation matches,
and rely on `tests/unit/test_agent_backends_parity.py` to catch drift.

## Implementation sketch (ordered)

1. `transport/config.py` line 74: add `"kas"` to `_ACP_BACKEND_VALUES`; update
   the `_validate_acp_backend` message tail.
2. `transport/lifecycle.py` ~1843: add the `elif GA_CREW_ACP_BACKEND == "kas":`
   branch writing `acp_backend = "kas"`.
3. `scripts/lib/agent_backends.sh`: add `kas` to the valid backend set.
4. Tests: KAS accepted, unknown still rejected, parity holds.
5. `docs/configuration.md`: document `kas` (Preview, bundled, no login).

## Risks / Trade-offs

- **Preview/insider status** — KAS is not GA in 0.9.0-insider.4. The
  `acp_backend=kas` config key is inferred from the claude/codex pattern; it
  must be verified against the 0.9.0 gateway's actual config schema before
  shipping (verification task in tasks.md).
- **Model mapping (D3)** — per-agent `gpt-5.6-luna` may not route sensibly under
  KAS. Left as an open question; could degrade task quality if KAS silently
  remaps or ignores the model.
- **Low urgency** — KAS is not the default upstream and ghostship's default
  (`kiro`) is unaffected, so this is not blocking the 0.9.0 image bump. It
  becomes required when KAS reaches GA or an operator opts in.

## Open questions

- Is the gateway config key literally `agent.acp_backend` with value `"kas"`,
  matching the claude/codex convention? Verify against the 0.9.0 gateway.
- Does KAS honour a per-agent `model` field, or does it route to a fixed KAS
  model regardless? Determines whether a follow-up ticket for the agent JSON
  `model` fields is needed.
- Does KAS require any gateway-side enablement (e.g. Developer Mode, as OpenCode
  does) that ghostship must set or document?
