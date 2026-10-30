# Design — TRN-289 Crew Dashboard Asset Proxy Compression Passthrough

## Context

See `proposal.md — Root Cause` for the full failure chain. Summary:

The transport proxies crew UI assets via `_handle_crew_ui_proxy` using
`_async_http.stream()` (raw byte passthrough). The crew gateway at
`gs-{id}:5476` is a standard Vite/KiroCrew HTTP server that honours
`Accept-Encoding` in the request. When the browser sends
`Accept-Encoding: gzip, br`, the gateway returns a gzip-compressed response
with `Content-Encoding: gzip`.

The transport strips `Content-Encoding` from all proxied responses via
`_HOP_BY_HOP_HEADERS` (to prevent the receiving browser from trying to
decompress already-decompressed content — correct when httpx decompresses).
But `_async_http.stream()` does **not** decompress — it streams raw bytes.
The result: compressed bytes arrive at the browser labelled as `text/javascript`
with no encoding hint. The browser's `<script>` evaluator sees binary garbage.

## Problem Decomposition

Two approaches exist:

### Option A — Decompress on the transport side

Strip `Content-Encoding` as now, but actually decompress the body before
streaming it. This means:

1. Buffer the full response body (`aread()` instead of `stream()`)
2. Detect `Content-Encoding: gzip` or `br`
3. Decompress with `zlib` / `brotli`
4. Stream the decompressed bytes

**Problems:**
- Requires buffering potentially large responses, defeating streaming
- Adds `brotli` as a new dependency for Brotli decompression
- Increases complexity of `_handle_crew_ui_proxy` significantly
- Any future encoding (zstd) requires another code path

### Option B — Prevent compression at the source (chosen)

Add `"accept-encoding"` to `_STRIPPED_CREW_PROXY_HEADERS`. This strips the
browser's `Accept-Encoding` header before the request reaches the crew gateway.
The gateway has no encoding preference to honour, so it returns plain
uncompressed content. Nothing needs to change on the response path.

**Why this is correct:**
- `_STRIPPED_CREW_PROXY_HEADERS` already exists for exactly this purpose —
  headers the transport cannot or should not forward as-is (`host`, `cookie`,
  `authorization`, `x-transport-token`)
- The transport is a middleman, not the terminal client — it should negotiate
  encoding based on what it can handle, not blindly forward the browser's
  preference
- No buffering, no new dependencies, no response-path complexity

## Decision

**Option B.** Add `"accept-encoding"` to `_STRIPPED_CREW_PROXY_HEADERS`.

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

## Risks / Trade-offs

- **Slightly larger responses from the crew gateway.** Assets are served
  uncompressed over the container network. All traffic is loopback/container-
  internal (never public internet), so the bandwidth cost is negligible.
- **Not a problem for direct dedicated-port access.** When the browser connects
  directly to `gs-{id}:5476` via the dedicated Caddy port, the transport is not
  in the path — compression negotiates normally and works correctly. Only the
  transport-proxied path is affected.

## Scope

One line change in `transport/server.py`. No other files touched.
