# Tasks: trn-113-kirocrew-050-upgrade

> Implementation order matters. Step 1 must complete (and the DB must be confirmed correct)
> before Steps 2–3 change any image pin. Steps 5–7 are validation-only; if the files are
> already correct, the task is just confirming that and checking the box.

---

## Step 1 — Re-verify the pre-seeded kiro-cli migration DB (highest risk — do this first)

`crews/_base/graduation/seed_kiro_db.py` hard-codes the exact SQLite schema and migration rows
that kiro-cli 2.20.0 / KiroCrew 0.4.0 ships. If 0.5.0's kiro-cli added rows or changed the
schema, a stale pre-seed causes silent DB-migration failures inside crews. Verify before bumping
any pin.

- [ ] Pull `ghcr.io/kirodotdev/kirocrew:0.5.0` locally (`podman pull ghcr.io/kirodotdev/kirocrew:0.5.0`).
- [ ] Start a throwaway container from the 0.5.0 image and let kiro-cli initialise its DB
  (e.g. `podman run --rm -it ghcr.io/kirodotdev/kirocrew:0.5.0 bash -c "kiro-cli --version; python3 -c \"import sqlite3; c=sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())\""`)
- [ ] Record the `(count, max_version)` returned and compare against the current seed expectation
  `(10, 9)` in `crews/_base/graduation/seed_kiro_db.py` (top-of-file docstring and the last
  `INSERT INTO migrations` row).
- [ ] **If count or max_version changed**: open `crews/_base/graduation/seed_kiro_db.py`,
  inspect `CREATE TABLE migrations` for any schema difference, and add any new
  `INSERT INTO migrations (version, name, applied_at) VALUES (...)` rows to match the 0.5.0
  image exactly.
- [ ] **If schema changed** (new tables, columns, or indexes): update the corresponding
  `CREATE TABLE` / `CREATE INDEX` / `CREATE UNIQUE INDEX` statements in `seed_kiro_db.py`.
- [ ] Update the version banner in `seed_kiro_db.py` top-of-file docstring from
  `kiro-cli 2.20.0 / KiroCrew 0.4.0` to the correct kiro-cli version found in the 0.5.0 image.
- [ ] Update the version banner in the `FRAGILITY WARNING` comment block in
  `crews/_base/graduation/Containerfile` (lines 14–33) to reference KiroCrew 0.5.0.
- [ ] **If no changes were needed**: note "schema and row count unchanged at (10, 9)" in the
  commit message so the next upgrader can see this was verified, not skipped.

---

## Step 2 — Bump the crew base image pin

- [ ] In `crews/_base/admission/Containerfile`, find the `FROM ghcr.io/kirodotdev/kirocrew:0.4.0`
  line and change it to `FROM ghcr.io/kirodotdev/kirocrew:0.5.0`.
- [ ] In the same file, find the `# Pinned to 0.4.0` comment near the `FROM` line and update it
  to `# Pinned to 0.5.0`.

---

## Step 3 — Bump the ephemeral login-container image pin

- [ ] In `config/ghostship.conf.example`, change `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.4.0`
  → `KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:0.5.0`.
- [ ] Verify that `transport/config.py`'s `kc_base_image` field has no hard-coded `0.4.0` default
  that would override the config value (the default should flow from the env/config, not be
  hard-coded in Python). If a hard-coded default exists, update it.
- [ ] Verify `scripts/install.sh` compose template or `KC_BASE_IMAGE` default line (if any) also
  references `0.5.0` so login containers and crew containers run the same KiroCrew minor.

---

## Step 4 — Refresh stale version references in cleanup + docs

- [ ] In `scripts/uninstall.sh` around line 106, update the human-readable cleanup message string
  `ghcr.io/kirodotdev/kirocrew:0.4.0` → `ghcr.io/kirodotdev/kirocrew:0.5.0`.
- [ ] In `academy/mcp/README.md`, update the sentence that reads
  `"to prevent KiroCrew 0.4.0 from pooling…"` → `"to prevent KiroCrew 0.5.0 from pooling…"`.
- [ ] In `config/ghostship.conf.example`, update the `GA_CREW_AGENT` comment
  `"Must be non-empty (KiroCrew 0.4.0 requires it)"` → `"(KiroCrew 0.5.0 requires it)"`.
- [ ] Add an entry to `CHANGELOG.md` under a new `## [0.3.x]` (or appropriate next version) header:
  bump KiroCrew base image from 0.4.0 → 0.5.0; note pre-seeded DB re-verified; call out the
  TRN-113 ticket.

---

## Step 5 — Validate governance-policy templates against 0.5.0's stricter validator

0.5.0 now hard-fails on a misspelled `sandbox` key or a malformed `publish` section in
`security_policy.json` (previously silently ignored). The three policy templates are the source
for the injected policy.

- [ ] Read `academy/policies/default.json` — confirm no `sandbox` key is present (or, if present,
  it is spelled correctly per the 0.5.0 schema); confirm no `publish` section is present or, if
  present, it is a valid object. If already correct, check this box — no edit required.
- [ ] Read `academy/policies/strict.json` — same check. Check this box when confirmed clean.
- [ ] Read `academy/policies/research.json` — same check. Check this box when confirmed clean.
- [ ] Confirm that `transport/container_scripts/inject_policy.py` lines 71–86 (the
  `trust_keys.ghostship` signature-verification path) still match 0.5.0's governance API
  (no renamed fields, no changed key path). If the call signature is unchanged, check this box.

---

## Step 6 — Validate agent specs against 0.5.0's stricter spec reader

0.5.0 refuses (rather than silently skips) malformed agent specs: a non-object spec, a symlink
into a sensitive location, or a file exceeding the size ceiling is now a hard failure.

- [ ] Read `academy/agents/ghost.json` — confirm it is a valid JSON object, is not a symlink, and
  is under any size ceiling documented in the 0.5.0 release notes. Check this box when confirmed.
- [ ] Read `academy/agents/spectre.json` — same check.
- [ ] Read `academy/agents/banshee.json` — same check.
- [ ] Read `academy/agents/wraith.json` — same check.
- [ ] Read `academy/agents/reaper.json` — same check.
- [ ] Read `academy/agents/raven.json` — same check.

---

## Step 7 — Validate MCP pooling behaviour under 0.5.0

`transport/lifecycle.py` ~lines 618–675 auto-injects `poolable: false` on any MCP entry that
carries a `headers` field, to prevent KiroCrew from pooling auth-bearing HTTP servers. 0.5.0
changed MCP isolation to a private backend per client ("misbehaving servers get isolated
per-connection"). Confirm the auto-injection is still correct and sufficient.

- [ ] Read `transport/lifecycle.py` lines 618–675 (`_copy_agents` / mcp.json writer) and confirm
  the `poolable: false` injection logic is intact and still applies to `headers`-bearing entries.
- [ ] Identify any crew compositions in `academy/mcp/` that wire a `headers`-bearing MCP server
  (e.g. `playwright.json` or any entry with an `"Authorization"` / `"x-api-key"` header).
- [ ] For each `headers`-bearing server found: confirm that `poolable: false` is correctly
  injected at runtime by tracing through the lifecycle code (no runtime test needed — a code
  read is sufficient). Check this box when confirmed.
- [ ] If no `headers`-bearing servers are wired in the current academy catalogue, note that and
  check this box — the code path is still exercised but the runtime impact is zero.
- [ ] Confirm 0.5.0 still honours the `poolable` field (check release notes / changelog for
  any removal or rename). If honoured unchanged, check this box.

---

## Step 8 — Rebuild and full test pass

- [ ] Run `scripts/install.sh` to rebuild the full image stack:
  `base-admission` → `_base` → each crew composition (`spec-ops`, `_worker`) and the transport.
  Confirm all layers build without error.
- [ ] Run the unit + integration suite: `tests/run.sh`. All tests must pass. Pay particular
  attention to `test_lifecycle.py`, `test_container_scripts.py`, `test_academy.py`, and
  `test_install_config.sh`.
- [ ] Launch a live crew (any composition). Confirm gateway readiness: `POST /login` (or API-key
  path) completes, `startup_complete` is reached, and the dashboard loads.
- [ ] Confirm token mint: `lifecycle.py` `_mint_cookie` (the `kirocrew token` call) succeeds and
  returns a valid `mc_token_<port>` cookie.
- [ ] Confirm cron reseed: `_reseed_crew_schedules` completes without error at crew start.
- [ ] Dispatch a minimal smoke task to each persona and confirm each reaches the agent and
  produces a result (no prompt-block, no wedged task). Use a trivial read-only task for each,
  e.g. `"List the files in /home/kirocrew/workplace and report back."` — the goal is to confirm
  the agent starts and completes, not to do real work.
- [ ] Confirm mail delivery works: send a test mail via `maildeliver` inside the crew and confirm
  delivery to the target mailbox.
- [ ] Confirm a git bundle round-trip: run `evac` and `supply` and confirm the bundle transfers
  and unpacks correctly.
- [ ] Confirm policy injection: check that `inject_policy.py` completes without error and the
  resulting `security_policy.json` is accepted by the 0.5.0 gateway (no policy-validation error
  in the gateway log).
