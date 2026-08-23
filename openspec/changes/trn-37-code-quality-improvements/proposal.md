## Why

`transport/server.py` contains a cluster of latent bugs — invalid JSON
serialization of `float("inf")`, missing thread-safety on a shared cache,
incorrect cron scheduling, a threading double-lock gap, and dead code —
that can cause subtle runtime failures or hide real errors in production.
TRN-37 resolves all findings from the code-quality audit before the 0.1.0
release freeze.

## What Changes

- **F-01** Replace `float("inf")` with sentinel `9_999_999_999.0` in
  `_advance_next_fire_at` and in schedule-monitor comparisons so
  `json.dumps` never sees a non-finite float.
- **F-02** Add a `threading.Lock` around reads and writes of
  `_host_memory_cache` to prevent a data race between the idle-monitor
  and request-handler threads.
- **F-03** Investigate whether MCP sync tool handlers run in the asyncio
  event loop or a thread-pool executor; if in the event loop,
  `time.sleep(3)` in `pickup`/`_pickup_list` blocks all concurrent
  requests. Document the finding or apply a fix (event loop → swap to
  `asyncio.sleep`, thread pool → no change needed).
- **F-05** Remove the unused `container_exec_pty` / `container_exec_pty_stdin`
  methods from `PodmanClient` (replaced by `container_exec_pty_stdin`
  during the OAuth refactor; the older overload is unreachable).
- **F-06** Eliminate the double-lock gap in `_append_captain_mail`: the
  registry is read under `_registry_lock`, released, then re-acquired to
  write — a second caller can slip in between and corrupt
  `last_captain_message_id`. Fix with a single held-lock read-modify-write.
- **F-08** Fix the cron-expression branch of `_advance_next_fire_at`:
  currently always advances by +60 s regardless of the expression. Use
  `croniter` (already in the dependency set) to compute the true next
  fire time, or add a `# TODO` if `croniter` is unavailable and document
  as a known limitation.
- **F-09** Replace `assert container.startswith("gs-")` / `assert
  vol.startswith("gs-vol-")` guards in `nuke` with explicit
  `RuntimeError` so they survive `-O` (optimised byte-code).
- **F-10** Call `_patch_crew_config` inside `_reconcile_registry`'s
  restart path so crews restored after a transport restart inherit the
  current config patches (currently only applied on fresh start).
- **F-11** Improve the warning in `_load_or_create_file_secret` to
  include the path that could not be written, aiding ops diagnosis.
- **F-12** Add `encoding='utf-8'` to `open()` calls inside inline
  container scripts to avoid platform-dependent codec surprises.
- **F-13** Use `container_archive_put` (the proper tar-based copy API) in
  `_copy_agents` / `_copy_skills` instead of f-string base64 embedding to
  eliminate quote-injection risk on filenames containing special characters.
- **F-14** Add a docstring or inline comment documenting the `HOST`
  environment variable (default `"0.0.0.0"`) in `server.py`.
- Remove `_login_flags()` and `_initiate_login()` dead code left over
  from the device-auth refactor.

## Capabilities

### New Capabilities

- `crew-lifecycle`: Behavioural requirements for crew bootstrap and
  registry reconciliation — specifically: `_patch_crew_config` must be
  applied during the reconcile restart path, and `_reconcile_registry`
  must be idempotent across transport restarts.

### Modified Capabilities

<!-- No existing spec files are present in this repo; the only net-new
     spec-level behaviour is in the bootstrap/registry domain above. -->

## Impact

- **`transport/server.py`**: All changes are confined to this file.
- **`croniter`**: Dependency confirmed present (used elsewhere); no new
  package additions required.
- **No API surface changes**: All affected functions are internal helpers
  (`_advance_next_fire_at`, `_host_memory_cache`, `nuke`, `_append_captain_mail`,
  `_reconcile_registry`, etc.). The public MCP tool signatures and REST
  routes are unchanged.
- **Behavioural change in `nuke`**: `RuntimeError` instead of silent
  pass under `-O` — observable only in optimised deployments, which is
  the desired outcome.
- **`pickup` / `_pickup_list` sleep**: If the audit (F-03) determines
  these run on the event loop, `time.sleep` will be replaced with
  `asyncio.sleep`; this is a threading/concurrency fix, not an API change.
