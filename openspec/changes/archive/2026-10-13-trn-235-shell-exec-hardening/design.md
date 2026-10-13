# Design

## Context

See proposal.md. Three shell-exec patterns replaced with `container_archive_put`; `Config.__repr__` hardened.

## Goals

- Eliminate shell exec from all credential injection paths
- Prevent credential values appearing in log output via repr

## Non-Goals

- Changing the credential delivery mechanism (Podman secrets) — that's TRN-211 scope
- Removing the chunking entirely from large payloads — `container_archive_put` handles size natively

## Decisions

### D1 — Replace chunk-loop with single container_archive_put call

Current `_inject_claude_auth` pattern: base64 encode tar → split into 4KB chunks → append each via `sh -c printf >> tmp` → `base64 -d < tmp | tar -x`. 

New pattern: pass the tar bytes directly to `container_archive_put`:

```python
# Build the tar in memory (already done — tar_bytes exists)
podman.container_archive_put(
    container,
    path="/home/kirocrew/.claude/",
    data=tar_bytes,  # raw tar bytes, not base64
)
```

`container_archive_put` is already implemented (`transport/podman.py`) and used in other injection paths. The base64 encoding step is eliminated along with the chunking loop and the tmp file cleanup.

Same pattern applies to `_inject_codex_auth` — it's structurally identical.

### D2 — Replace python3 -c cookie write with container_archive_put

Current `_write_dashboard_cookie`:
```python
podman.container_exec(container, ["python3", "-c", f"... open(p,'w').write({cookie!r}) ..."])
```

New pattern: build a minimal tar in memory containing one file (the cookie value), mode 0600, and call `container_archive_put`. This is exactly how `_finish_crew_setup` writes other files.

```python
import io, tarfile
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w") as tf:
    cookie_bytes = cookie.encode()
    info = tarfile.TarInfo(name=".dashboard_cookie")
    info.size = len(cookie_bytes)
    info.mode = 0o600
    tf.addfile(info, io.BytesIO(cookie_bytes))
podman.container_archive_put(container, path="/home/kirocrew/.kiro/crew/", data=buf.getvalue())
```

### D3 — Config.__repr__ masking

Add a `__repr__` to the `Config` dataclass:

```python
_SENSITIVE_FIELDS = {"kiro_api_key", "anthropic_api_key", "openai_api_key", "claude_code_oauth_token"}

def __repr__(self) -> str:
    fields = []
    for f in dataclasses.fields(self):
        val = getattr(self, f.name)
        if f.name in _SENSITIVE_FIELDS and val:
            val = "***"
        fields.append(f"{f.name}={val!r}")
    return f"Config({', '.join(fields)})"
```
