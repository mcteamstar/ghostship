## Why

Transport config is scattered across 35+ `os.environ.get("X", default)` calls throughout `server.py`, with defaults duplicated across `install.sh`, `ghostship.conf.example`, and `docs/configuration.md`. A new env var added to `server.py` but missed in `install.sh` works in dev but silently never takes effect in production. There is no single place to audit what config the transport actually reads.

## What Changes

- Create `transport/config.py` with a `Config` dataclass holding all transport runtime configuration and defaults
- Replace all `os.environ.get()` calls in `server.py` with `cfg.<field>` reads from a single `Config` instance loaded at startup
- Update `config/ghostship.conf.example` to match the full `Config` field list (single source-of-truth audit)
- Update `docs/configuration.md` to reflect any gaps found in the audit
- Add a CI test that validates every `Config` field is present in `ghostship.conf.example`

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `config-file`: the set of supported runtime configuration variables is now authoritatively defined by `Config` in `transport/config.py`; `ghostship.conf.example` and `docs/configuration.md` must stay in sync with it (CI-enforced)

## Impact

- `transport/config.py` — new file
- `transport/server.py` — all `os.environ.get()` calls replaced with `cfg.<field>` reads; no behaviour changes
- `config/ghostship.conf.example` — updated to match `Config` fields
- `docs/configuration.md` — updated to close any gaps found
- `tests/unit/` — new test asserting `Config` fields and `conf.example` are in sync
