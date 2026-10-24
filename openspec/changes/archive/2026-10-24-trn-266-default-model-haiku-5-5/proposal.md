# Proposal: Change global default model to claude-haiku-5-5

## Context

The current default model for all six academy agent personas (`ghost`, `spectre`,
`banshee`, `reaper`, `wraith`, `raven`) is `gpt-5.6-luna`, hardcoded in each
persona's `academy/agents/<name>.json` `model` field. The global config fallback
(`model.default` / `KC_MODEL_DEFAULT`) in `config/ghostship.yaml.example` is also
unset (empty), meaning KiroCrew's own built-in falls through when no override or
per-backend default is configured.

The desired default is `claude-haiku-5-5` — the cheapest Anthropic tier available
at 0.06x credit cost for requests up to 100K tokens — which is a strong fit for
the high-volume, fast-turnaround agentic work ghostship crews do.

## What changes

1. **Per-agent model fields** — update `"model"` in all six
   `academy/agents/*.json` files from `"gpt-5.6-luna"` to `"claude-haiku-5-5"`.

2. **Config default fallback** — set `model.default: "claude-haiku-5-5"` in
   `config/ghostship.yaml.example` (currently `""`). This makes the intent
   explicit at the config layer even when operators do not set any override.

3. **Documentation** — update `README.md` (two mentions) and
   `docs/configuration.md` (scenario examples that reference `gpt-5.6-luna`) to
   name `claude-haiku-5-5` as the new default.

## What does NOT change

- No existing `backends.<b>.model.override` or `backends.<b>.model.default`
  entries are touched.
- The `config/ghostship.yaml` local install config is not changed (it has a
  `kiro` backend override to `claude-sonnet-4.6` which takes precedence anyway).
- No transport logic, config parsing, or precedence chain is altered.

## Precedence context

The per-agent field (level 3) and `model.default` (level 5) are the two lowest
knobs an operator can set above the KiroCrew built-in. Both are changed to
`claude-haiku-5-5` so that a default install uses Haiku regardless of whether an
operator sets an explicit `model.default` in their own config or not.

```
dispatch(model=…)            # 1. unchanged
  └─ backends.<b>.model.override  # 2. unchanged — operators keep their lock
       └─ per-agent model          # 3. gpt-5.6-luna → claude-haiku-5-5
            └─ backends.<b>.model.default  # 4. unchanged
                 └─ model.default          # 5. "" → "claude-haiku-5-5"
                      └─ KiroCrew built-in # 6. unchanged
```
