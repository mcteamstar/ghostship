## Context

See `proposal.md` - Why for motivation. Current state, confirmed by inspection this session:

- `transport/test_*.py` (6 files: `test_crew_types.py`, `test_file_transfer.py`, `test_security_hardening.py`, `test_self_healing.py`, `test_transport.py`, `test_verify_admiral_sig.py`) — Python `unittest`, discovered today via `python3 -m unittest discover -s transport -p "test_*.py"` (the exact command `.github/workflows/test.yml` runs, and the exact command hardcoded into `openspec/specs/transport-test-coverage/spec.md`'s "Test suite runs safely inside crew containers" requirement).
- Only 2 of those 6 files (`test_transport.py`, `test_file_transfer.py`) contain `@unittest.skipUnless(shutil.which("podman"/"git"), ...)`-guarded classes/methods — the rest are unconditionally pure. The guarded classes are *mixed into the same files* as pure unit classes, not split into separate files.
- `test_transport.py` already contains a dual import-resolution shim for loading the server module:
  ```python
  try:
      from transport.test_file_transfer import server   # package-style, needs repo root on sys.path
  except ModuleNotFoundError:
      from test_file_transfer import _install_import_stubs   # flat, needs transport/ on sys.path
      _install_import_stubs()
      server = importlib.import_module("transport.server")
  ```
  No `transport/__init__.py` exists — `transport` resolves today only as a Python 3 implicit namespace package, contingent on the repo root being on `sys.path`. That happens today as a side effect of `python3 -m unittest discover -s transport ...` being invoked via `python3 -m`, which prepends the current working directory (the repo root, if invoked from there) to `sys.path`.
- `tests/*.sh` at the repo root (`test_install_config.sh`, `test_dedicated_transport.sh`) plus `MANUAL_TEST_DEDICATED_MACHINE.md` — bash integration tests requiring a real Podman socket/machine, run manually today, never wired into CI. `tests/test_install_config.sh` predates every other test file in the repo (it shipped in the initial commit).
- No test files are copied into any Containerfile (`crews/_base/*`, `crews/spec-ops`, `transport/Containerfile`) — confirmed by grep this session. Relocation has no image-build-time dependency to account for.

## Goals / Non-Goals

**Goals:**
- One root `tests/` location for every suite, one orchestrator entry point.
- Preserve exactly today's self-skip behavior (Podman/git-dependent tests skip cleanly when their dependency is absent) and today's CI coverage — no regression in what's tested or how gracefully it degrades.
- A real (even if initially tiny) home for E2E tests, since this session's manual smoke test proved that category catches bugs the others can't.

**Non-Goals:**
- Wiring the bash integration suite or any E2E suite into CI. `ubuntu-latest` has no dedicated Podman machine set up today, and this change is about *location and orchestration*, not standing up new CI infrastructure. CI keeps running exactly the unit category it runs today, just through the new orchestrator.
- Splitting `test_transport.py`/`test_file_transfer.py`'s mixed pure/guarded classes into separate files by category. Their existing per-class/method `skipUnless` guards already make the *whole file* behave correctly in both environments — forcing a file-level unit/integration split would mean either duplicating skip logic or breaking up files that are fine as they are, for no behavioral gain.
- Rewriting the tests themselves. This is a location and invocation change, not a test-content change.

## Decisions

**Directory layout: `tests/unit/` (the 6 relocated `.py` files, unchanged as a group), `tests/integration/` (the 2 existing bash scripts), `tests/e2e/` (new, placeholder), `tests/manual/` (the existing manual-test doc).** The Python files move together as one group into `unit/` rather than being split by class, per the Non-Goal above — the group's own self-skip behavior already gives correct results in both Podman-present and Podman-absent environments, which is what "unit" needs to mean here operationally (safe to run anywhere, more thorough when infra is present) rather than "zero classes ever touch Podman." Alternative considered: a finer-grained `tests/unit/` + `tests/integration/` split at the class level — rejected as the Non-Goal explains, pending real evidence it's worth the churn.

**Import resolution: standardize on the package-style path (`transport.server`), guaranteed by having the orchestrator always invoke discovery with an explicit top-level directory at the repo root (`-t .`), not by continuing to rely on the accidental `python3 -m` cwd-prepend behavior.** `transport/server.py` isn't moving, so `transport` staying resolvable as a namespace package (repo root on `sys.path`) is untouched by this change — only the test files move. Making `-t .` explicit in the orchestrator (rather than implicit via `-m`'s cwd side effect) makes this robust to however the orchestrator itself gets invoked. The existing flat-import fallback branch in `test_transport.py` becomes dead code once this is guaranteed; removing it is listed as an optional cleanup task, not required for this change to be correct (leaving it doesn't break anything — it just never fires).

**Orchestrator: a single `tests/run.sh` bash script, category flags (`--unit`, `--integration`, `--e2e`), default (no flags) runs all three, one aggregate summary and exit code.** Chosen over a Makefile (adds a new tool dependency for no real benefit here) or a Python-based runner (the integration suite is bash-native; a bash orchestrator can shell out to both bash scripts and `python3 -m unittest` equally easily, whereas a Python orchestrator shelling out to bash scripts gains nothing). Each category runs as a subprocess; the orchestrator captures each one's exit code, prints a per-category result line, and exits non-zero if any invoked category failed — never masking a failure by only checking the last category run.

**CI: update `.github/workflows/test.yml` to call `tests/run.sh --unit`, changing nothing about what CI actually covers.** This preserves today's exact CI behavior and coverage while moving the invocation onto the new shared entry point. Wiring integration/E2E into CI is explicitly deferred (see Non-Goals) — worth a follow-up change once there's a concrete plan for CI-side Podman provisioning (Linux CI runners don't need the macOS VM machinery `install.sh` uses, so a Linux-only integration CI job is plausible future work, just not this change).

## Risks / Trade-offs

- [Risk] Moving files changes their git history's apparent location, and `git mv` alone doesn't guarantee `git log --follow` picks up cleanly for every reviewer's tooling. → Mitigation: use `git mv` (not remove+recreate) for every file so Git's rename detection has the best chance, and mention the relocation explicitly in the commit message.
- [Risk] The import-resolution change (standardizing on `-t .`) is exactly the kind of thing that "works on my machine" and then breaks for a different invocation style (e.g., someone running `python3 -m unittest discover` from inside `tests/unit/` directly instead of through the orchestrator). → Mitigation: the orchestrator is the one documented, supported entry point; document in `tests/unit/README.md` (or a header comment) that direct invocation needs the same `-t .` flag, and keep the existing fallback import branch as a safety net rather than deleting it in this change (see optional cleanup task).
- [Risk] Silent scope creep into "let's also write real E2E tests now." → Mitigation: this change's job is the placeholder and the orchestrator wiring, not authoring new E2E test content — tasks.md should make the placeholder itself (even a trivial always-passing or explicitly-skipped test) the definition of done for that piece, with real E2E test authoring as separate future work.

## Migration Plan

1. `git mv` the 6 `transport/test_*.py` files into `tests/unit/`.
2. `git mv` the 2 bash scripts and the manual-test doc into `tests/integration/` and `tests/manual/` respectively (they're already under `tests/`, just being organized into subdirectories).
3. Add the `tests/e2e/` placeholder.
4. Add `tests/run.sh`.
5. Update `.github/workflows/test.yml`.
6. Update `openspec/specs/transport-test-coverage/spec.md` per this change's delta (done at archive time, not before).
7. Run the full suite locally (both with and without Podman available, if practical) to confirm no regression before merging.

Rollback: revert the commit; nothing outside `tests/`, `transport/`, and the workflow file is touched, so rollback is a plain `git revert`.
