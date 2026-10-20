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

Ghostship should not own a per-backend path table — that belongs in `.agents`. Staging into `.agents/skills/`, `.agents/context/`, `.agents/mcp/` and running `setup <backend>` keeps all path knowledge in one place. When `.agents` adds opencode support, ghostship gets it automatically.

Alternative considered: AcademyLoader reads the path table from `.agents` and writes directly. Rejected — duplicates the format conversion logic (especially MCP format per backend) and couples ghostship to `.agents` internals.

### D3: MCP delivery stays at launch time

Catalogue entries contain `${VAR}` references resolved from the transport's runtime environment (API keys, transport URL). These cannot be resolved at image build time. The staging step writes raw resolved JSON into `.agents/mcp/`; `setup` handles the per-backend format conversion.

### D4: .agents/setup called once per launch, not per kind

A single `setup <backend>` call handles skills, steering, and MCP in one pass. This matches how operators use `.agents` locally and avoids partial-wiring states if one kind fails mid-delivery.

### D5: Containerfile clones .agents as the kirocrew user

`/home/kirocrew/.agents` is owned by kirocrew. The clone runs as the kirocrew user (or files are chowned) so `setup` can write to `~/.kiro/`, `~/.claude/` etc. without permission issues.

## Risks / Trade-offs

- **`.agents/setup` container compatibility** → `.agents/setup` is tested on developer machines (macOS/Linux) where harness CLIs are installed. Inside a container, `kiro-cli` exists but `claude` and `codex` CLIs may or may not be present depending on the composition. `setup` must handle missing CLIs gracefully (it already skips undetected harnesses). Risk is low; mitigation is a container smoke-test in CI.
- **Symlinks vs real files** → `.agents/setup` creates symlinks on developer machines. At bake time the source directories exist, so symlinks resolve correctly and are baked as real files. At launch-time injection the source is a tar archive delivered by `container_archive_put` — files land as real files, not symlinks. This is the desired behaviour; no special handling needed.
- **`.agents` repo pin** → The crew image bakes a specific commit of `.agents`. If path conventions change in `.agents`, a crew image rebuild is needed. Mitigation: pin by tag/SHA in the Containerfile and bump deliberately.
- **MCP format divergence** → `.agents/setup` currently writes kiro-format `mcp.json`. Claude and opencode formats differ. If `.agents/setup` does not yet handle the MCP format for a given backend, those crews get no MCP wiring. Mitigation: implement MCP support in `.agents` before or alongside this change; document as a known gap until done.

## Migration Plan

1. Update `mcteamstar/.agents/setup` to handle container context (no-op if harness CLI absent)
2. Add `.agents` clone to all composition Containerfiles
3. Refactor `AcademyLoader`: replace `_copy_skills`, `_copy_steering`, and MCP delivery with staging + `setup <backend>` exec
4. Pass `acp_backend` from the registry entry into `AcademyLoader` at launch (already available via `_finish_crew_setup`)
5. Existing kiro crews: next relaunch re-runs `AcademyLoader` and picks up the new flow; no migration needed for running crews
6. Rollback: revert `AcademyLoader` changes; the `.agents` clone in the image is inert if `AcademyLoader` never calls `setup`

## Open Questions

- Does `.agents/setup` need a `--no-symlink` flag for container use, or does baking at image-build time mean symlinks are already resolved before the container runs? (Current understanding: bake-time clone + real-file tar injection at launch = no symlink issue. Confirm during implementation.)
- Should `setup` be called idempotently on every launch (safe, slightly slower) or only on first launch (requires tracking state)? Current proposal: every launch, since content changes with each academy update.
