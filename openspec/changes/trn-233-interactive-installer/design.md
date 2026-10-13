# Design

## Context

See proposal.md. Adds an interactive guided setup mode to `install.sh` triggered when no `ghostship.conf` exists.

## Goals

- Zero friction first-run: backend chosen, credentials collected, images built, login done, harness wired — all in one `./install.sh`
- Non-interactive path unchanged for existing operators

## Non-Goals

- TUI (dialog/whiptail) — plain read prompts only
- Multi-backend interactive setup (stretch goal for later)
- Windows/WSL support (out of scope for this change)

## Decisions

### D1 — Detection trigger

```bash
if [[ ! -f ghostship.conf && ! -f config/ghostship.conf ]] || [[ "${1:-}" == "--setup" ]]; then
    _interactive_setup
fi
```

Checked before any other processing. `--setup` forces interactive mode even with an existing conf (useful for re-configuring).

### D2 — Prompt helper pattern

```bash
_prompt() {
    local prompt="$1" default="$2" var_name="$3"
    read -r -p "${prompt} [${default}]: " value
    value="${value:-$default}"
    printf -v "$var_name" '%s' "$value"
}
```

All prompts use `read -r -p`. Defaults shown in brackets. Empty input accepts default.

### D3 — Credential prompts per backend

| Backend | Prompts |
|---------|---------|
| kiro | `KIRO_IDENTITY_PROVIDER` (builderid/sso/idc), `KIRO_REGION` |
| claude | Choose: `CLAUDE_CODE_OAUTH_TOKEN` (recommended) or `ANTHROPIC_API_KEY`. If token: instructions to run `claude setup-token` first. |
| codex | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL` |

### D4 — ghostship.conf write

Collected values written to `config/ghostship.conf` (creating `config/` if needed) using `>>` to append only the collected settings. Existing file not overwritten — the detection check ensures we only reach here when no conf exists.

### D5 — Login flow after transport starts

After the transport reaches the "ready" health-check, call `ghostship auth login` (which is `scripts/install.sh`'s own login trigger, not a separate process). This reuses the existing `_wait_for_login` infrastructure already in install.sh.

### D6 — Harness registration

```bash
_prompt "Register MCP server with detected harnesses? (kiro-cli, claude, opencode)" "y" confirm
if [[ "$confirm" == "y" || "$confirm" == "Y" ]]; then
    ghostship setup
fi
```

`ghostship setup` is idempotent — safe to skip or re-run.
