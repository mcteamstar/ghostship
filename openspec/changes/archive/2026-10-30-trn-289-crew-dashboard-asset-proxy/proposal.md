# Proposal

## Why

When a crew is launched with `dashboard=True`, the per-crew KiroCrew dashboard
is accessible at a dedicated Caddy port (e.g. `localhost:64058/`). Loading the
SPA at that URL fails with:

```
Uncaught SyntaxError: Invalid or unexpected token (in /assets/main-DtG7OZ5a.js:1:2)
```

The browser receives the JS asset as 573 KB of valid text (`const __vite__mapDep...`)
when fetched directly via `fetch()`, but the `<script>` tag that executes the
same asset during page load gets binary garbage (`U+FFFD` replacement characters)
causing a parse failure.

## Root Cause

The transport proxy chain is:

```
browser → :64058/ → Caddy (caddy.py) → transport:64057/crews/{id}/ui{path} → gs-{id}:5476/
```

The transport's `_handle_crew_ui_proxy` strips certain headers from the
**response** before passing it to the browser (`_HOP_BY_HOP_HEADERS`, which
includes `content-encoding`). This is correct when httpx decompresses the body
— but the transport uses `_async_http.stream()` which streams the raw bytes
without decompressing.

The real problem is on the **request** side: the browser sends
`Accept-Encoding: gzip, br` in the request. The transport forwards this header
unchanged to the crew gateway (`gs-{id}:5476`). The gateway honours it and
returns a gzip-compressed response with `Content-Encoding: gzip`. The transport
then strips `Content-Encoding` from the response headers (hop-by-hop) without
decompressing the body. The browser receives 129 KB of gzip binary labelled as
`text/javascript` with no `Content-Encoding` header telling it to decompress →
parse failure.

Direct `fetch()` calls work because the Fetch API decompresses transparently
inside the browser. The `<script>` tag evaluation fails because by the time the
compressed bytes reach the JS engine, the content-type and content-encoding
metadata that would trigger browser-side decompression has been lost.

## What Changes

Strip `accept-encoding` from the outbound proxy request in
`_STRIPPED_CREW_PROXY_HEADERS` so the crew gateway always returns uncompressed
content. This is the minimal, correct fix — it prevents the mismatch between
what the gateway sends and what the transport passes through.

## Capabilities

### Modified Capabilities

- `crew-ui-proxy`: Add a requirement that the transport MUST strip
  `Accept-Encoding` from proxied requests to crew gateways, so that gateways
  never return compressed responses that the transport cannot transparently
  pass through.

## Impact

- `transport/server.py` — add `"accept-encoding"` to `_STRIPPED_CREW_PROXY_HEADERS`
- No changes to `caddy.py`, `install.sh`, `ga-radar`, or any other component
