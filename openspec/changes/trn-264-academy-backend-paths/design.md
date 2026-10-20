# Design

## Context

See proposal.md — Why. Current state: `AcademyLoader` in `transport/academy.py` hardcodes kiro destination paths (`~/.kiro/skills/`, `~/.kiro/steering/`, `~/.kiro/mcp.json`) via tar-injection. The crew's `acp_backend` is already recorded in the registry (TRN-259) and passed through to launch. `mcteamstar/.agents` exists and its `setup` script already has a tested per-backend path table and format converters for kiro, claude, opencode, and codex.

## Goals / Non-Goals

**Goals:**
- Skills, steering, and MCP reach the correct harness paths for kiro, claude, and codex backend crews
- Adding a new backend requires no ghostship changes — only `mcteamstar/.agents/setup`
- Crew images remain backend-agnostic; the crew image does not need to know which backend it will run

**Non-Goals:**
- Delivering agent persona JSON to non-kiro backends (kiro-specific concept, no equivalent)
- Changing the academy content store structure or the install-time rsync
- Runtime hot-reload of academy content without relaunch
- opencode backend (no `launch --backend opencode` support yet; `.agents/setup opencode` support is a free side-effect once the backend exists)

## Decisions

### D1: .agents cloned into crew image at build time, not at launch time

Baking `.agents` into the image means `setup` is always available without a network call at launch. Content (skills, steering) is still injected at launch from the transport bind-mounts, which change with each ghostship upgrade without requiring an image rebuild. The `.agents` repo changes infrequently (path table updates) and a rebuild is cheap.

Alternative considered: clone at launch time. Rejected — adds network dependency to the critical launch path and a latency hit on every crew start.

### D2: AcademyLoader stages into .agents/ then execs setup, rather than writing directly to harness paths

Ghostship's academy is responsible for injecting content — not delivering it. `AcademyLoader` stages into `.agents/skills/`, `.agents/context/`, and `.agents/mcp/servers.json`, then calls `setup <backend>`. All delivery path knowledge, format conversion, and per-backend wiring lives in `.agents/setup`. Ghostship never needs to know about `~/.claude/rules/`, `~/.kiro/mcp.json`, or any harness-specific paths.

Alternative considered: AcademyLoader writes directly to harness paths. Rejected — duplicates delivery logic that `.agents` already owns, couples ghostship to per-backend path conventions, and means every new backend requires ghostship changes.

### D3: MCP delivered via .agents/mcp/servers.json

After env-var substitution, resolved catalogue entries are written as `.agents/mcp/servers.json` inside the container (the same format `.agents/setup` already reads via `load_mcp_servers()`). Each entry includes `"disabled": false` so academy-delivered servers are active by default. `setup <backend>` then writes the backend-native MCP config (kiro `mcp.json`, claude `.claude.json`, codex `config.toml`) from that single source. No MCP format conversion in ghostship.

### D4: .agents/setup called once per launch, not per kind

A single `setup <backend>` call handles skills, steering, and MCP in one pass. This matches how operators use `.agents` locally and avoids partial-wiring states if one kind fails mid-delivery.

### D5: Containerfile clones .agents as the kirocrew user

`/home/kirocrew/.agents` is owned by kirocrew. The clone runs as the kirocrew user (or files are chowned) so `setup` can write to `~/.kiro/`, `~/.claude/` etc. without permission issues.

## Risks / Trade-offs

- **`.agents/setup` container compatibility** → `setup` creates symlinks on developer machines. At bake time source dirs exist so symlinks resolve and are baked as real files. At launch-time, `AcademyLoader` tar-injects real files into `.agents/skills/` and `.agents/context/`, overwriting the baked symlinks — the harness paths then point to real files. Risk is low; mitigation is a container smoke-test in CI.
- **`disabled: true` default in `.agents`** → `load_mcp_servers()` defaults new servers to `disabled: true`. `AcademyLoader` sets `"disabled": false` on every entry it writes to `servers.json` so academy-delivered servers are active. This is the only ghostship-side MCP concern.
- **`.agents` repo pin** → The crew image bakes a specific commit of `.agents`. Path convention changes in `.agents` require a crew image rebuild. Mitigation: pin by tag/SHA in the Containerfile and bump deliberately.

## Migration Plan

1. Verify `mcteamstar/.agents/setup` handles missing harness CLIs gracefully (it already skips undetected harnesses — confirm in a container context)
2. Add `.agents` clone to all composition Containerfiles
3. Refactor `AcademyLoader`: replace `_copy_skills`, `_copy_steering`, and MCP delivery with staging + `setup <backend>` exec
4. Pass `acp_backend` from the registry entry into `AcademyLoader` at launch (already available via `_finish_crew_setup`)
5. Existing kiro crews: next relaunch re-runs `AcademyLoader` and picks up the new flow; no migration needed for running crews
6. Rollback: revert `AcademyLoader` changes; the `.agents` clone in the image is inert if `AcademyLoader` never calls `setup`


