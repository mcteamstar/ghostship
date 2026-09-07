## Context

See `proposal.md — Why` for motivation.

Five `hmac.new()` call sites exist across three files in the `transport/` package.
All five already supply all three positional arguments (`key`, `msg`, `digestmod`),
so the change is purely syntactic: the deprecated alias is replaced with `hmac.new()`
using explicit keyword arguments for `digestmod` to make intent clear and suppress
deprecation warnings in Python 3.12+.

Call-site inventory (from `grep -rn "hmac.new" transport/`):

| File | Line | Current form |
|------|------|--------------|
| `transport/files.py` | 184 | `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` |
| `transport/files.py` | 224 | `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` |
| `transport/files.py` | 242 | `hmac.new(_FILE_SECRET.encode(), payload.encode(), hashlib.sha256)` |
| `transport/captain.py` | 227–230 | multi-line, already explicit third arg |
| `transport/container_scripts/inject_policy.py` | 52 | `hmac.new(secret.encode("utf-8"), payload, hashlib.sha256)` |

## Goals / Non-Goals

**Goals:**
- Remove all uses of the deprecated `hmac.new()` alias
- Maintain identical HMAC digest output at every call site
- Improve call-site readability by using `digestmod=` keyword argument

**Non-Goals:**
- Changing the key derivation, digest algorithm, or any payload construction
- Modifying test code or adding new tests (no behaviour change)
- Touching any file outside `transport/`

## Decisions

**Decision: use `hmac.new(key, msg, digestmod=hashlib.sha256)` form**

`hmac.new` is documented as deprecated but not yet removed; the replacement is
`hmac.HMAC(key, msg, digestmod)`. However, the difference is only the entry point —
`hmac.new` delegates to `hmac.HMAC` internally. Either form is acceptable for
a maintenance fix. Using `hmac.new(...)` with an explicit `digestmod=` keyword
argument is the minimal change that (a) keeps the diff small, (b) makes the algorithm
explicit at the call site, and (c) is semantically identical. Ghost (the implementer)
may choose `hmac.HMAC` instead — both are correct; the tasks.md notes the option.

**Alternatives considered:**
- `hmac.HMAC(key, msg, digestmod)` — equally valid, slightly larger diff due to
  renaming the entry point; acceptable if preferred by the implementer.
- No change at runtime — rejected; deprecation warnings will eventually become errors.

## Risks / Trade-offs

- **Risk: digest values change** → Not possible — `hmac.new` is an alias; the computed
  bytes are identical. Verified by reading the CPython source.
- **Risk: import statement needs updating** — `hmac` is already imported in all three
  files; no import change required.
- **Risk: missed call site** — `grep -rn "hmac.new" transport/` found exactly five;
  the grep output is the authoritative list for this task.

## Migration Plan

1. Edit the five call sites in order: `transport/files.py` (3), `transport/captain.py`
   (1), `transport/container_scripts/inject_policy.py` (1).
2. Run the existing test suite to confirm no regressions.
3. Commit with message referencing TRN-125.
4. No rollback plan required — the change is purely additive/syntactic and immediately
   reversible by reverting the commit.
