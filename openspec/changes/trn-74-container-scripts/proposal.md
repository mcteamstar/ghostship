## Why

`transport/server.py` contains 14 `python3 -c "..."` exec calls, each constructing a Python script as an inline string and running it inside a crew container via `podman exec`. This includes auth injection/extraction/wipe, mail delivery and counting, model patching, OpenSpec seeding, steering copy, and admiral secret write. Unit tests mock `container_exec_checked` but don't validate the script content — a typo in a script or a wrong SQLite field name only fails at runtime inside a container. The `_read_subjects_src` workaround base64-encodes and `exec()`s a script purely to avoid shell quoting issues, which is the worst form of the pattern.

## What Changes

- Create `transport/container_scripts/` directory with individual `.py` files for each of the 14 operations
- Update `transport/Containerfile` to copy the `container_scripts/` directory into the image
- Replace all 14 `python3 -c "..."` exec calls in `server.py` with `python3 /scripts/<name>.py [args]` invocations
- Scripts that take parameters use `sys.argv` or `argparse` — no more dynamic string construction
- The `_read_subjects_src` base64-encode-and-exec pattern is eliminated — file-based invocation solves the quoting problem it was working around
- Add unit tests that import the script files directly and test their logic without any container mock

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — pure structural refactor. No externally visible behaviour changes.

## Impact

- `transport/container_scripts/` — new directory with ~14 `.py` files
- `transport/Containerfile` — adds `COPY container_scripts/ /scripts/` (or similar)
- `transport/server.py` — 14 `python3 -c` call sites replaced with `python3 /scripts/<name>.py`
- `tests/unit/` — new test cases for the script files themselves (no container mock needed)
- Natural prerequisite for TRN-71 (modularisation): extracting scripts clarifies the Containerfile `COPY` pattern before the module split changes it further
