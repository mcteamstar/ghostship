# Tasks — TRN-289 Crew Dashboard Asset Proxy Compression Passthrough

## T1 — Add `accept-encoding` to `_STRIPPED_CREW_PROXY_HEADERS` ✅

In `transport/server.py`, add `"accept-encoding"` to the
`_STRIPPED_CREW_PROXY_HEADERS` frozenset:

```python
_STRIPPED_CREW_PROXY_HEADERS: frozenset[str] = frozenset({
    "host",
    "cookie",
    "authorization",
    "x-transport-token",
    # Strip Accept-Encoding so the crew gateway never sends compressed
    # responses. The transport streams raw bytes without decompressing,
    # so forwarding Accept-Encoding causes the browser to receive
    # compressed content with no Content-Encoding header.
    "accept-encoding",
})
```

**Implemented in commit `49a2bf2`.**

## T2 — Verify fix ✅

Confirmed via direct fetch from the proxied path:

```
first4: [99, 111, 110, 115]  →  "cons"  →  "const ..."  →  valid JS
isGzip: false
size: 573851
```

Prior to fix, the same fetch with `Accept-Encoding: gzip` forwarded returned
129 KB of gzip binary with `content-encoding` stripped, causing
`SyntaxError: Invalid or unexpected token` at position 1:2.
