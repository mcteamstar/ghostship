## Context

`transport/server.py` has 35+ scattered `os.environ.get("X", default)` calls. The same variable names and defaults appear in `install.sh`, `ghostship.conf.example`, and `docs/configuration.md` with no automated check keeping them in sync.

## Goals / Non-Goals

**Goals:** Single source of truth for all transport runtime config. No behaviour changes. Make config testable via `Config(field=value)` construction.

**Non-Goals:** Change any env var names, defaults, or semantics. Address TRN-71 modularisation concerns. Move `install.sh` config (shell-side vars) into Python.

## Decisions

### Config dataclass approach

**Decision:** Use a `@dataclass` in `transport/config.py` with typed fields and default values matching current `os.environ.get()` defaults. Load it once at module level in `server.py` via `cfg = Config.from_env()`.

`dataclasses` is stdlib — no new dependency. A `from_env()` classmethod reads all env vars in one place and constructs the instance. This keeps the dataclass itself pure (testable without env) and the env-reading logic in one explicit location.

Alternative considered: `pydantic.BaseSettings`. Rejected — adds a dependency, and the existing code is simple enough that stdlib suffices.

### Field naming

**Decision:** Field names mirror the env var names lowercased (e.g. `GA_MAX_CREWS` → `ga_max_crews`). This makes the mapping mechanical and grep-able.

### CI sync check

**Decision:** A unit test loads `Config` via introspection, extracts all field names, and checks each has a corresponding commented entry in `ghostship.conf.example`. This is a simple string search — no need to parse shell syntax.

### Ordering of changes relative to TRN-77

TRN-77 adds `GA_GIT_AUTHOR_NAME` and `GA_GIT_AUTHOR_EMAIL`. If TRN-75 ships first, TRN-77 adds those fields to `Config`. If not, TRN-77 adds them directly to `server.py`. Either order is safe.

## Risks / Trade-offs

- `Config` becomes a large flat dataclass (~35+ fields). Acceptable for now; TRN-71 will group related fields by module when it splits the codebase.
- Any test that mocks `os.environ` directly will need updating to pass a `Config` instance instead. Expected scope: small.

## Migration Plan

Pure refactor — no externally visible changes. Deploy replaces the container; no data migration needed.
