# Design: Change global default model to claude-haiku-5-5

## Files affected

### 1. `academy/agents/*.json` — 6 files

Each file has a top-level `"model"` field. The value `"gpt-5.6-luna"` is replaced
with `"claude-haiku-5-5"` in all six:

- `academy/agents/ghost.json`
- `academy/agents/spectre.json`
- `academy/agents/banshee.json`
- `academy/agents/reaper.json`
- `academy/agents/wraith.json`
- `academy/agents/raven.json`

No other fields in these files are touched.

### 2. `config/ghostship.yaml.example`

The `model.default` key currently has an empty string value:

```yaml
model:
  default: ""
```

Change to:

```yaml
model:
  default: "claude-haiku-5-5"
```

The comment block above it already explains the semantics; no comment changes are
needed.

### 3. `README.md` — 2 occurrences

| Location | Current | New |
|:---------|:--------|:----|
| Feature description (line ~26) | `Agents default to \`gpt-5.6-luna\`` | `Agents default to \`claude-haiku-5-5\`` |
| Prerequisites callout (line ~51) | `Ghostship defaults to \`gpt-5.6-luna\`, which requires a Pro subscription or higher.` | `Ghostship defaults to \`claude-haiku-5-5\`, which requires a Pro subscription or higher.` |

### 4. `docs/configuration.md` — scenario/scenario examples

The two scenario references to `gpt-5.6-luna` in the per-agent context appear in
the `yaml-config` spec scenarios used as illustrative examples. These are in
`docs/configuration.md` in the Model precedence section. Update any example that
names `gpt-5.6-luna` as the per-agent model to use `claude-haiku-5-5`.

## Deployment note

This change takes effect for **newly launched crews** — existing running crews
were already launched with the old model patched into their `config.local.json`.
Restart (nuke + relaunch) any crew that should pick up the new default.

Crews with an active `backends.<b>.model.override` in their transport config are
unaffected (override beats per-agent model and `model.default`).
