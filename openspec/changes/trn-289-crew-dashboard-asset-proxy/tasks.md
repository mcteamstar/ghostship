# Tasks — TRN-289 Crew Dashboard Asset Proxy Compression Passthrough

## T1 — Add `accept-encoding` to `_STRIPPED_CREW_PROXY_HEADERS`

- [x] In `transport/server.py`, add `"accept-encoding"` to the
  `_STRIPPED_CREW_PROXY_HEADERS` frozenset so the crew gateway never receives
  an `Accept-Encoding` header and always returns uncompressed content.

  Implemented in commit `49a2bf2`.

## T2 — Add unit test for Accept-Encoding stripping

- [x] In `tests/unit/test_server.py`, add a test that verifies `accept-encoding`
  is stripped from proxied crew requests. The test should confirm that when a
  request with `Accept-Encoding: gzip, br` arrives at the crew UI proxy, the
  outbound request to the crew gateway does NOT include an `Accept-Encoding`
  header.
