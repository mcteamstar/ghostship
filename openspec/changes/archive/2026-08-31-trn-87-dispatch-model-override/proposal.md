## Why

KiroCrew's own `/api/spawn` and `/api/crons` endpoints already accept a per-call `model` field that pins the model for that one spawn or scheduled job only — overriding the persona's configured model (`academy/agents/*.json`) and the crew-wide `KC_MODEL_OVERRIDE`/`KC_MODEL_DEFAULT` env vars without touching either. Ghostship's `dispatch`, `schedule`, and `captain(action="order")` tools build their own request bodies to these endpoints and never forward a `model` field, so today the only way to change what model a task runs on is to edit a persona's agent JSON before launch (crew-wide for that persona) or set an env var (crew-wide for every persona). There is no way to say "run just this one task on a different model" — useful for a one-off that needs a stronger (or cheaper) model than the persona's default, without touching shared crew config.

## What Changes

- Add an optional `model` string parameter to the `dispatch` MCP tool. When provided, it is forwarded as `model` in the `/api/spawn` request body for that task only; when omitted, behavior is unchanged (persona config / env var precedence applies as today).
- Add the same optional `model` parameter to `schedule` (`cron`, `interval`, and one-shot `delay` job creation alike — these build separate request bodies in `transport/server.py` and all three need the field) and to `captain(action="order")`, forwarded as `model` in the `/api/crons` request body for that job only. Retain the pin in Ghostship's schedule registry, reuse it for restart re-seeding and transport-owned schedule-monitor ticks, and pass it to any `fire_immediately` first run.
- Validate `model` transport-side before forwarding: reject non-string values and cap length, mirroring the bounds KiroCrew itself enforces (`_MODEL_NAME_RE`, `MAX_SHORT_STRING`) so a malformed value fails fast with a clear transport error instead of a raw 400 from the crew gateway.
- No change to precedence for tasks that omit `model` — `KC_MODEL_OVERRIDE` > per-agent `model` > `KC_MODEL_DEFAULT` > KiroCrew built-in remains exactly as documented in `transport/lifecycle.py`. A per-dispatch `model`, when the caller sets it, is a **new tier above all of these** — it wins even over `KC_MODEL_OVERRIDE`, because `KC_MODEL_OVERRIDE` works by patching the same per-agent config field (`academy/agents/*.json`'s `model`) that KiroCrew's own per-spawn `model` param is documented to override (`subagent.py`'s `requested_model`: the per-spawn pin wins over the config pin whenever it's non-empty, with no special case for how that config pin was set). **This is an intentional trade-off, not a bug**: `KC_MODEL_OVERRIDE` stops being an absolute ceiling once per-call overrides exist. See design.md's Risks section.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `task-orchestration`: `dispatch`, `schedule`, and `captain(action="order")` gain an optional per-call `model` parameter forwarded to the crew gateway for that task/job only.

## Impact

- `transport/server.py`: `dispatch()` (~line 2444), `schedule()`, and `captain()` — add `model` parameter, validation, registry persistence, and forwarding into the `/api/spawn` / `/api/crons` request bodies.
- `transport/lifecycle.py`: retain scheduled model pins when reconciling/re-seeding existing jobs and when the transport-owned schedule monitor fires a due task.
- `tests/unit/test_server.py` (or equivalent): coverage for `model` forwarded when present, omitted when absent, and rejected when malformed.
- `.claude-plugin/skills/ghostship-command/SKILL.md`: document the new `model` parameter on `dispatch`/`schedule`/`captain`.
- No KiroCrew-side changes required — both endpoints already accept and validate `model`.
