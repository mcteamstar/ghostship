"""Tests for trn-52-rate-limiting: the RateLimiter primitive, the
RateLimitMiddleware ASGI layer, and the GA_RATE_LIMIT_* env-var wiring.

Each test names the spec scenario it exercises. Uses the same dependency-free
import stub harness as the other transport tests (stubs mcp/starlette/httpx).
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import threading
import unittest

from transport import security as sec

# Import server through the shared stub harness (stubs mcp/starlette/httpx).
from tests.unit.test_file_transfer import server


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run_asgi(mw, scope):
    """Drive an ASGI middleware once and return the list of sent messages."""
    collected: list[dict] = []

    async def _send(msg):
        collected.append(msg)

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(mw(scope, _receive, _send))
    return collected


def _http_scope(method="GET", path="/mcp", headers=None, client=("1.2.3.4", 5555)):
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "client": client,
        "query_string": b"",
    }


class _RecordingApp:
    """Inner ASGI app that records whether it was called and sends a 200."""

    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        })
        await send({"type": "http.response.body", "body": b"inner-ok"})


# ── 4.1 RateLimiter.record ────────────────────────────────────────────────────

class TestRateLimiterRecord(unittest.TestCase):
    def test_allows_up_to_max_then_denies(self):
        """Within limit — allowed; at the limit — the next is denied."""
        rl = sec.RateLimiter(max_requests=3, window_secs=60.0)
        t0 = 1000.0
        self.assertTrue(rl.record("k", now=t0))
        self.assertTrue(rl.record("k", now=t0))
        self.assertTrue(rl.record("k", now=t0))
        # 4th within the window is denied and not recorded.
        self.assertFalse(rl.record("k", now=t0))

    def test_is_limited_is_read_only(self):
        """is_limited checks without recording."""
        rl = sec.RateLimiter(max_requests=1, window_secs=60.0)
        t0 = 2000.0
        self.assertFalse(rl.is_limited("k", now=t0))
        # A pure check must not consume the single slot.
        self.assertFalse(rl.is_limited("k", now=t0))
        self.assertTrue(rl.record("k", now=t0))
        self.assertTrue(rl.is_limited("k", now=t0))

    def test_window_slides_old_timestamps_expire(self):
        """Window slides — old requests expire and admit new ones."""
        rl = sec.RateLimiter(max_requests=2, window_secs=10.0)
        t0 = 3000.0
        self.assertTrue(rl.record("k", now=t0))
        self.assertTrue(rl.record("k", now=t0))
        self.assertFalse(rl.record("k", now=t0))  # at limit
        # After the full window has elapsed, the old hits are pruned.
        self.assertTrue(rl.record("k", now=t0 + 11))

    def test_prune_removes_empty_key(self):
        """_prune removes the key entirely once its list is empty."""
        rl = sec.RateLimiter(max_requests=5, window_secs=10.0)
        t0 = 4000.0
        rl.record("k", now=t0)
        self.assertIn("k", rl._hits)
        # A prune well past the window empties and drops the key.
        rl._prune("k", t0 + 100)
        self.assertNotIn("k", rl._hits)

    def test_keys_are_independent(self):
        """Distinct keys have independent buckets."""
        rl = sec.RateLimiter(max_requests=1, window_secs=60.0)
        t0 = 5000.0
        self.assertTrue(rl.record("a", now=t0))
        self.assertTrue(rl.record("b", now=t0))
        self.assertFalse(rl.record("a", now=t0))


# ── 4.2 RateLimiter thread safety ─────────────────────────────────────────────

class TestRateLimiterThreadSafety(unittest.TestCase):
    def test_concurrent_record_never_exceeds_max(self):
        """Concurrent record() at the boundary never admits past max_requests."""
        max_requests = 50
        rl = sec.RateLimiter(max_requests=max_requests, window_secs=300.0)
        threads_count = 8
        per_thread = 40
        allowed = [0] * threads_count
        barrier = threading.Barrier(threads_count)

        def worker(idx):
            barrier.wait()
            count = 0
            for _ in range(per_thread):
                if rl.record("shared"):
                    count += 1
            allowed[idx] = count

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(threads_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_allowed = sum(allowed)
        # Exactly max_requests admitted, never more.
        self.assertEqual(total_allowed, max_requests)
        self.assertEqual(len(rl._hits["shared"]), max_requests)


# ── 4.3 / 4.4 RateLimitMiddleware pass-through and 429 ─────────────────────────

class TestRateLimitMiddleware(unittest.TestCase):
    def test_within_limit_passes_to_inner_app(self):
        """Request within limit reaches the inner app and returns its response."""
        inner = _RecordingApp()
        limiters = {"mcp": sec.RateLimiter(max_requests=2, window_secs=60.0)}
        mw = server.RateLimitMiddleware(inner, limiters=limiters, api_key="")
        msgs = _run_asgi(mw, _http_scope(method="POST", path="/mcp"))
        self.assertTrue(inner.called)
        start = next(m for m in msgs if m["type"] == "http.response.start")
        self.assertEqual(start["status"], 200)

    def test_over_limit_returns_429_and_skips_inner(self):
        """Over limit — 429 with Retry-After; inner app not invoked."""
        limiters = {"mcp": sec.RateLimiter(max_requests=1, window_secs=45.0)}
        inner = _RecordingApp()
        mw = server.RateLimitMiddleware(inner, limiters=limiters, api_key="")

        # First call consumes the single slot.
        _run_asgi(mw, _http_scope(method="POST", path="/mcp"))
        self.assertTrue(inner.called)

        # Second call is over the limit — 429, inner not called again.
        inner.called = False
        msgs = _run_asgi(mw, _http_scope(method="POST", path="/mcp"))
        self.assertFalse(inner.called)
        start = next(m for m in msgs if m["type"] == "http.response.start")
        self.assertEqual(start["status"], 429)
        headers = {k: v for k, v in start["headers"]}
        self.assertEqual(headers[b"retry-after"], b"45")
        self.assertEqual(headers[b"content-type"], b"text/plain; charset=utf-8")
        body = next(m for m in msgs if m["type"] == "http.response.body")
        self.assertIn(b"Rate limit exceeded", body["body"])
        self.assertIn(b"45 seconds", body["body"])

    def test_unmatched_path_passes_through(self):
        """A path with no registered limiter passes through with no rate check."""
        inner = _RecordingApp()
        # Only /mcp is limited; /logout is not.
        limiters = {"mcp": sec.RateLimiter(max_requests=1, window_secs=60.0)}
        mw = server.RateLimitMiddleware(inner, limiters=limiters, api_key="")
        for _ in range(5):
            inner.called = False
            _run_asgi(mw, _http_scope(method="POST", path="/logout"))
            self.assertTrue(inner.called)

    def test_non_http_scope_passes_through(self):
        """Non-HTTP scopes (e.g. lifespan) pass through unchanged."""
        inner = _RecordingApp()
        limiters = {"mcp": sec.RateLimiter(max_requests=1, window_secs=60.0)}
        mw = server.RateLimitMiddleware(inner, limiters=limiters, api_key="")

        async def _noop_send(msg):
            return None

        asyncio.run(mw({"type": "lifespan"}, None, _noop_send))
        self.assertTrue(inner.called)

    def test_match_endpoint_priority(self):
        """_match_endpoint returns the right key per priority order."""
        m = server.RateLimitMiddleware._match_endpoint
        self.assertEqual(m("POST", "/login"), "login_post")
        self.assertEqual(m("GET", "/login"), "login_get")
        self.assertEqual(m("GET", "/files/abc"), "files")
        self.assertEqual(m("POST", "/crews/demo/api/spawn"), "crew_api")
        self.assertEqual(m("GET", "/mcp"), "mcp")
        self.assertEqual(m("GET", "/mcp/messages"), "mcp")
        self.assertIsNone(m("POST", "/logout"))
        self.assertIsNone(m("GET", "/crews/demo/ui/app"))

    def test_caller_key_ip_only_without_bearer(self):
        """No bearer token — the key is the source IP alone."""
        mw = server.RateLimitMiddleware(None, limiters={}, api_key="")
        scope = _http_scope(headers=[])
        self.assertEqual(mw._caller_key(scope, None), "1.2.3.4")

    def test_caller_key_hash_prefix_with_bearer(self):
        """Bearer token — the key is SHA-256(token)[:8]:<ip>, raw token absent."""
        mw = server.RateLimitMiddleware(None, limiters={}, api_key="")
        scope = _http_scope(headers=[(b"x-forwarded-for", b"9.9.9.9, 10.0.0.1")])
        token = "supersecret-token"
        key = mw._caller_key(scope, token)
        expected_prefix = hashlib.sha256(token.encode()).hexdigest()[:8]
        self.assertEqual(key, f"{expected_prefix}:9.9.9.9")
        self.assertNotIn(token, key)

    def test_same_ip_different_tokens_separate_buckets(self):
        """Same IP, different tokens — distinct limiter keys (separate buckets)."""
        mw = server.RateLimitMiddleware(None, limiters={}, api_key="")
        scope = _http_scope()
        k1 = mw._caller_key(scope, "token-A")
        k2 = mw._caller_key(scope, "token-B")
        self.assertNotEqual(k1, k2)


# ── 4.5 Exempt paths ──────────────────────────────────────────────────────────

class TestExemptPaths(unittest.TestCase):
    def test_health_and_version_never_limited(self):
        """/health and /version pass through regardless of call count."""
        inner = _RecordingApp()
        limiters = {"mcp": sec.RateLimiter(max_requests=1, window_secs=60.0)}
        mw = server.RateLimitMiddleware(inner, limiters=limiters, api_key="")
        for path in ("/health", "/version"):
            for _ in range(50):
                inner.called = False
                msgs = _run_asgi(mw, _http_scope(method="GET", path=path))
                self.assertTrue(inner.called)
                # No 429 ever emitted for exempt paths.
                self.assertFalse(
                    any(
                        m.get("status") == 429
                        for m in msgs
                        if m["type"] == "http.response.start"
                    )
                )


# ── 4.6 _parse_rate_limit_var ─────────────────────────────────────────────────

class TestParseRateLimitVar(unittest.TestCase):
    def setUp(self):
        self._name = "GA_RATE_LIMIT_TEST_TRN52"
        os.environ.pop(self._name, None)

    def tearDown(self):
        os.environ.pop(self._name, None)

    def test_valid_value_parsed(self):
        """A valid '60:60' parses to (60, 60)."""
        os.environ[self._name] = "60:60"
        self.assertEqual(server._parse_rate_limit_var(self._name, 10, 10), (60, 60))

    def test_unset_returns_default(self):
        """Unset var falls back to the default without warning."""
        self.assertEqual(server._parse_rate_limit_var(self._name, 7, 11), (7, 11))

    def test_malformed_returns_default_and_warns(self):
        """Malformed input returns the default and logs a WARNING naming the var."""
        os.environ[self._name] = "notanumber"
        with self.assertLogs("transport.server", level="WARNING") as cm:
            result = server._parse_rate_limit_var(self._name, 60, 60)
        self.assertEqual(result, (60, 60))
        self.assertTrue(any(self._name in line for line in cm.output))

    def test_non_positive_returns_default_and_warns(self):
        """Zero / negative fields are rejected as a parse failure."""
        os.environ[self._name] = "0:60"
        with self.assertLogs("transport.server", level="WARNING") as cm:
            result = server._parse_rate_limit_var(self._name, 5, 300)
        self.assertEqual(result, (5, 300))
        self.assertTrue(any(self._name in line for line in cm.output))


# ── 4.7 _build_rate_limiters and master switch ────────────────────────────────

class TestBuildRateLimiters(unittest.TestCase):
    _VARS = [
        "GA_RATE_LIMIT_ENABLED",
        "GA_RATE_LIMIT_LOGIN_GET",
        "GA_RATE_LIMIT_LOGIN_POST",
        "GA_RATE_LIMIT_MCP",
        "GA_RATE_LIMIT_FILES",
        "GA_RATE_LIMIT_CREW_API",
    ]

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in self._VARS}

    def tearDown(self):
        for k in self._VARS:
            os.environ.pop(k, None)
            if self._saved.get(k) is not None:
                os.environ[k] = self._saved[k]

    def test_enabled_builds_five_limiters_with_defaults(self):
        """Default (enabled) build yields the six endpoint limiters."""
        limiters = server._build_rate_limiters()
        self.assertIsNotNone(limiters)
        self.assertEqual(
            set(limiters),
            {"login_get", "login_post", "mcp", "files", "crew_api", "dashboard_auth"},
        )
        # Defaults per spec.
        self.assertEqual(
            (limiters["login_post"].max_requests, int(limiters["login_post"].window_secs)),
            (5, 300),
        )
        self.assertEqual(
            (limiters["mcp"].max_requests, int(limiters["mcp"].window_secs)),
            (300, 60),
        )

    def test_override_applied(self):
        """A valid override reaches the built limiter."""
        os.environ["GA_RATE_LIMIT_MCP"] = "600:120"
        limiters = server._build_rate_limiters()
        self.assertEqual(limiters["mcp"].max_requests, 600)
        self.assertEqual(int(limiters["mcp"].window_secs), 120)

    def test_disabled_returns_none(self):
        """GA_RATE_LIMIT_ENABLED=false disables the middleware (returns None)."""
        os.environ["GA_RATE_LIMIT_ENABLED"] = "false"
        self.assertIsNone(server._build_rate_limiters())

    def test_disabled_is_case_insensitive(self):
        os.environ["GA_RATE_LIMIT_ENABLED"] = "FALSE"
        self.assertIsNone(server._build_rate_limiters())

    def test_enabled_true_default(self):
        os.environ["GA_RATE_LIMIT_ENABLED"] = "true"
        self.assertIsNotNone(server._build_rate_limiters())


if __name__ == "__main__":
    unittest.main()
