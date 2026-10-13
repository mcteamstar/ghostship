# Tasks

## 1. Update install.sh default and check logic

- [x] 1.1 In `scripts/install.sh`, change the default value of `GA_REQUIRE_API_KEY` written into the generated conf from `warn` to `error` (line ~140). Update the adjacent comment to reflect the new default and document `off` as the override for proxy-protected deployments. Verify: a fresh install without existing conf produces `GA_REQUIRE_API_KEY=error` in the written conf.
- [x] 1.2 Update the existing check at line ~829–836 to correctly handle the new default. When `HOST` is `127.0.0.1` or unset (loopback), skip the check entirely — no key required. When `HOST` is non-loopback and `GA_API_KEY` is unset and `GA_REQUIRE_API_KEY` is not `off`, abort with exit 1 and a clear error message. Verify: `HOST=0.0.0.0 GA_API_KEY="" ./install.sh` aborts before building images.

## 2. Update transport startup gate

- [x] 2.1 In `transport/server.py` (~line 544), update the `GA_REQUIRE_API_KEY` startup check: change the default from `warn` to `error`. When the effective value is `error` and the bind address is non-loopback and no API key is present, exit with a logged error. Keep the `off` path (skip all checks) and the `warn` path (log warning, continue) as-is for backward compatibility. Verify: unit test confirms transport exits on non-loopback without key when mode is `error`.

## 3. Update docs and conf.example

- [x] 3.1 In `config/ghostship.conf.example`, update the `GA_REQUIRE_API_KEY` entry: change default to `error`, update comment to explain `off` for proxy-protected deployments. Verify: the example accurately reflects the new default behaviour.
- [x] 3.2 In `docs/configuration.md`, update the `GA_REQUIRE_API_KEY` reference table row: new default `error`, document `off` escape hatch, note that `warn` is still accepted. Verify: docs match code behaviour.

## 4. Tests

- [x] 4.1 Add/update unit test in `tests/unit/` covering: (a) transport startup exits on non-loopback without key when `GA_REQUIRE_API_KEY=error`; (b) transport starts on loopback without key regardless of setting; (c) transport starts with `GA_REQUIRE_API_KEY=off` without key on non-loopback. Run `tests/run.sh --unit` and confirm pass.

## Workflow follow-up

- Archive the change after review.
