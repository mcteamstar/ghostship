# TRN-55 — Proxy query string CRLF sanitisation

## Background

The original SSRF finding (2026-08-25) had two parts:

1. **Crafted `crew_id` reaching arbitrary hosts on `ga-net`** — fixed. `_require_crew(crew_id)` now does a registry lookup and returns 404 for unknown crew IDs before any upstream connection is made.

2. **Query string CRLF injection** — still open. This is what this change addresses.

## Problem

Both `_handle_crew_ui_proxy` and `_handle_crew_api_proxy` forward the inbound query string to the upstream KiroCrew gateway verbatim:

```python
query = request.scope.get("query_string", b"")
if query:
    upstream_url = f"{upstream_path}?{query.decode('latin-1')}"
```

`latin-1` decoding preserves `\r` (0x0D) and `\n` (0x0A) as literal characters. If those characters appear in the query string, they are injected into the upstream HTTP request URL. Depending on the HTTP client library's behaviour, this could allow request splitting or header injection against the internal `gs-{crew_id}:5476` gateway.

In practice the risk is low — the upstream is an internal container on `ga-net`, not an external service — but it's a clean, small fix.

## Fix

Sanitise the query string bytes before forwarding: strip or reject any byte that is a control character (`0x00`–`0x1F`, `0x7F`). The minimal safe fix is to strip CR and LF; the conservative fix is to reject any control character and return 400.

Preferred approach: **strip control characters silently** (not reject). The KiroCrew UI and API are not expected to use control characters in query strings, and silent stripping avoids breaking legitimate clients with malformed query strings.

Extract a shared helper used by both proxy handlers:

```python
def _sanitise_query_string(raw: bytes) -> str:
    """Decode query string and strip control characters.

    latin-1 is used to preserve non-ASCII bytes faithfully (percent-encoded
    values in a query string are ASCII anyway). Control characters (0x00-0x1F,
    0x7F) are stripped to prevent CRLF injection into the upstream request.
    """
    return re.sub(r"[\x00-\x1f\x7f]", "", raw.decode("latin-1"))
```

Then in both handlers replace:

```python
# Before
upstream_url = f"{upstream_path}?{query.decode('latin-1')}"

# After
upstream_url = f"{upstream_path}?{_sanitise_query_string(query)}"
```

## Files

| File | Change |
|:-----|:-------|
| `transport/server.py` | Add `_sanitise_query_string()` helper; apply in `_handle_crew_ui_proxy` and `_handle_crew_api_proxy` |
| `tests/unit/test_server.py` | Add `TestProxyQuerySanitisation` — verify CR, LF, null stripped; normal query strings pass through unchanged |

## Effort

~20 lines of production code, ~30 lines of tests. Single commit.
