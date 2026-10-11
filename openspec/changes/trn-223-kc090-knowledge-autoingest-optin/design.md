# Design — TRN-223 Knowledge auto-ingest opt-in

## Context

KiroCrew 0.9.0 (PR #2448) flips knowledge auto-ingest from default-on to **opt-in**. The
affected paths are the file-watcher, the git commit hook, and clipboard capture. The
upgrade research report classifies this as **LOW IMPACT / no code change required** for
ghostship, because the source audit shows ghostship never relied on auto-ingest.

The grounding is entirely in three places in the repo:

1. `transport/lifecycle.py` — `_patch_crew_config()` builds a `full_overrides` dict and
   hands it to `patch_crew_config.py` to deep-merge into `config.local.json`.
2. `transport/container_scripts/patch_crew_config.py` — `patch_config()` /
   `_deep_merge()` performs the merge.
3. `crews/_base/graduation/seed_kiro_db.py` — pre-seeds the kiro-cli SQLite DB.

### What the source actually contains

`_patch_crew_config()` in `transport/lifecycle.py` (the `full_overrides` dict, roughly
lines 1885–1965) is the single place a crew's `config.local.json` is written. Its current
top-level sections are:

```python
full_overrides: dict[str, Any] = {
    "agent": agent_overrides,                       # agent name, memory gates, sandbox…
    "stt": {"enabled": False},                      # no microphone in a headless crew
    "session": {
        "eager_spawn": False,
        "timeout_secs": 300,
        "watchdog_rss_max_mb": 2000,
    },
    "telemetry": {"beacon_enabled": False},
    "auto_update": False,
    "orchestrator": {"max_plan_duration_seconds": 14400},
    "agents": {                                     # generated per deployed agent JSON
        af.stem: {
            "kiro_agent": af.stem,
            "memory_store": "default",
            "session_control": True,
            "member_dispatch": True,
        }
        for af in Path("/agents").glob("*.json")
        if _manifest_selects(manifest_agents, af.name)
    },
}
```

There is **no `knowledge` key**. The generated `agents` block sets `memory_store="default"`
per agent — that selects a memory store, it does not enable knowledge ingest.

`patch_crew_config.py::patch_config()` deep-merges whatever top-level sections it is given:

```python
def _deep_merge(base: dict, overrides: dict) -> dict:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base

def patch_config(config_path: str, full_overrides: dict) -> None:
    p = pathlib.Path(config_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    _deep_merge(cfg, full_overrides)
    p.write_text(json.dumps(cfg, indent=2))
```

So adding a top-level `"knowledge"` section needs **no patcher change** — the generic
deep-merge already writes it at the correct path.

`seed_kiro_db.py` seeds only `auth_kv`, `history`, `state`, and `migrations`
(six migration rows, versions 0–5). It creates no knowledge tables and inserts no
knowledge rows, so nothing in the seed references ingest.

## Goals / Non-Goals

**Goals:**
- Document that ghostship runs with knowledge auto-ingest disabled under 0.9.0+.
- Optionally pin the disabled posture explicitly so an upstream default flip cannot
  silently enable it (D1).
- Add a source-grounded assertion test so the posture cannot regress unnoticed.

**Non-Goals:**
- Turning auto-ingest on for any crew.
- Seeding knowledge data.
- Adding operator-facing env vars for knowledge.

## Decisions

### D1 — Pin `knowledge.auto_ingest=false` explicitly, or rely on the upstream default?

**Option A (defensive pin, recommended):** Add one top-level entry to `full_overrides` in
`_patch_crew_config()`, alongside the other fixed headless overrides:

```python
    "telemetry": {"beacon_enabled": False},
    "auto_update": False,
+   # Knowledge auto-ingest (file-watcher, git commit hook, clipboard capture) is
+   # opt-in as of KiroCrew 0.9.0 (PR #2448) and was never triggered in a headless
+   # crew anyway. Pin it off explicitly so a future upstream default flip cannot
+   # silently enable ingest from the mounted worktree.
+   "knowledge": {"auto_ingest": False},
    "orchestrator": {"max_plan_duration_seconds": 14400},
```

- *Pro:* survives both gateway upgrades and any future upstream default change; the
  posture is intentional and visible in one place next to `stt`/`telemetry`.
- *Con:* couples ghostship to the exact upstream key name/shape (`knowledge.auto_ingest`).
  If 0.9.0's real key differs (e.g. `knowledge.ingest.enabled` or a set of per-path
  booleans), the pin is a dead key. The key name here is taken from the research report's
  description of PR #2448 and MUST be verified against the 0.9.0 config schema before
  merge — see tasks.md task 2.

**Option B (track upstream default):** Change nothing in `full_overrides`; rely on
KiroCrew 0.9.0 shipping auto-ingest off by default.

- *Pro:* zero coupling to the upstream key name.
- *Con:* a later upstream default flip (or a config template that re-enables it) would
  silently turn ingest on inside crew containers with no ghostship guard.

**Decision:** Prefer **Option A**, *conditional on verifying the exact key name against the
0.9.0 config schema*. If the key name cannot be verified (schema not yet stable in the
insider build), fall back to Option B and record the open item, keeping only the
documentation and the "no implicit enablement" test. This mirrors the TRN-219 posture of
not pinning an upstream-schema value until it is verified against the actual base image.

### D2 — Where the key goes

If D1-A is accepted, the key is a **fixed, non-operator-configurable** override, placed in
the static part of `full_overrides` (not derived from a `GA_*` env var). This matches the
existing treatment of `stt.enabled=false` and `telemetry.beacon_enabled=false`, which are
headless-crew constants (see the design note "D1" referenced in TRN-213 and the
`full_overrides` comment block). No `config.py` field and no `ghostship.conf.example` entry
is added.

### D3 — Verification approach

A unit-style assertion test imports/parses `_patch_crew_config`'s override construction and
asserts:

- the generated `full_overrides` contains no key that enables ingest implicitly; and
- if D1-A is accepted, `full_overrides["knowledge"]["auto_ingest"] is False`.

Because `_patch_crew_config()` performs a `container_exec` and reads `/agents`, the test
should assert against the override-dict construction logic rather than invoking the full
function against a live container. The cleanest path is to assert on `patch_config()` end
state: build a representative `full_overrides` (including the knowledge key if D1-A),
run `patch_config()` against a temp file, and assert the written JSON has
`knowledge.auto_ingest == false` and leaves the other sections intact. This reuses the
real `_deep_merge()` rather than a mock.

## Risks

- **Wrong key name (primary risk).** The `knowledge.auto_ingest` key is inferred from the
  research report's prose summary of PR #2448, not from a verified 0.9.0 config dump. A
  wrong name makes the D1-A pin inert (silently). Task 2 verifies it against the base image
  before any pin lands; if unverifiable, drop to Option B.
- **Scope creep.** It is tempting to add operator knowledge knobs; this change explicitly
  does not (Non-Goals).

## Implementation sketch (if D1-A accepted)

1. In `transport/lifecycle.py`, add the `"knowledge": {"auto_ingest": False}` entry to the
   `full_overrides` literal in `_patch_crew_config()` (between `auto_update` and
   `orchestrator`), with the explanatory comment from D1.
2. No change to `patch_crew_config.py` — `_deep_merge()` already writes the section.
3. Add the assertion test (D3).
4. Add the `docs/configuration.md` note.
