## Context

`_finish_crew_setup` in `transport/server.py` bootstraps a new crew container.
Its step ordering accumulated organically as features were added rather than
being designed around actual dependencies. This caused a real race condition
where the admiral signing secret — auth material used by Raven to verify Admiral
mail — was injected after agents, skills, and steering were copied, well after the
post-restart gateway was live. A `captain()` call with `fire_immediately=True`
that dispatches Raven immediately after crew creation can land in the window between
"gateway live" and "secret injected", producing a signature verification failure.

Additionally the secret write lacked `os.fsync`, leaving a kernel-buffer window
where a near-simultaneous read (Raven starting up) returns empty or partial content.

## Goals / Non-Goals

**Goals:**
- Admiral secret is in place before the post-restart gateway is ever reachable
- Secret write is durable (fsync before close)
- Each step in `_finish_crew_setup` has an explicit dependency comment so future
  contributors don't accidentally break the ordering

**Non-Goals:**
- Changing what any step does — only when it runs
- Parallelising independent steps (out of scope; sequential is simpler and fast enough)
- Changing `_inject_policy` behaviour

## Decisions

### Move admiral secret injection to right after `_inject_auth`

The secret has no dependency on the gateway being up — it's a plain file write
into the container filesystem. `_inject_auth` is already doing filesystem work
(SQLite write). Grouping them together before the restart means both are committed
before pool workers start, and before any external process can trigger a Raven
check-in.

**Alternative considered:** inject secret at container image build time (static
secret). Rejected: the secret must be unique per crew and unknown to the image.

### Add `os.fsync(fd)` before `os.close(fd)`

The Python `os.write` + `os.close` pattern does not guarantee the write reaches
disk before `close` returns — the kernel may buffer it. `os.fsync` flushes the
buffer to the underlying storage, ensuring any concurrent `open` + `read` from
another process sees the full content. Cost: one extra syscall per crew launch,
negligible.

### Move `_inject_policy` to after `_seed_openspec_store`

`_inject_policy` only needs `admiral_secret` (already generated) and the
container filesystem. It currently runs after the post-restart gateway wait, but
has no gateway dependency. Moving it alongside the other filesystem ops
(`_copy_agents`, `_copy_skills`, etc.) groups like with like and makes the
dependency structure explicit.

### Add dependency comments to each step

The ordering bug existed because nothing documented *why* each step was where it
was. Each step in the revised `_finish_crew_setup` will have a one-line comment
stating its dependency (e.g. `# depends on: gateway (pre-restart)`), making
accidental reordering visible in code review.

## Risks / Trade-offs

**No behaviour change for the happy path** — all the same steps run, just in a
better order. Existing tests pass unchanged.

**Secret is now written before the restart** — the restart does a stop+start.
The secret file lives on the home volume, which persists across restarts, so it
survives. No issue.
