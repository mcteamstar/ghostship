"""Unit tests for bin/lib/caddy_install.py (installer Caddy config generator).

Note: tests/unit/test_caddy.py already covers transport/caddy.py (the
runtime Caddy portal helper). This file covers bin/lib/caddy_install.py, the
installer module that generates initial-config.json.

Tests run without a live Caddy process or any network access.

Coverage:
(a) TLS mode 'off' sets automatic_https.disable=True.
(b) With API key, routes include a 401 handler.
(c) Without API key, no 401 handler present.
(d) 'acme' mode includes the ACME domain in the TLS policy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bin.lib.caddy_install import CaddyConfig, generate_caddy_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(**kwargs) -> dict:
    """Return a generated caddy config dict for the given overrides."""
    config = CaddyConfig(**kwargs)
    return generate_caddy_config(config)


def _routes(doc: dict) -> list[dict]:
    return doc["apps"]["http"]["servers"]["ga-main"]["routes"]


def _tls(doc: dict) -> dict:
    return doc["apps"].get("tls", {})


def _route_ids(doc: dict) -> list[str]:
    return [r.get("@id", "") for r in _routes(doc)]


def _find_route(doc: dict, route_id: str) -> dict | None:
    for r in _routes(doc):
        if r.get("@id") == route_id:
            return r
    return None


# ---------------------------------------------------------------------------
# (a) TLS mode 'off' disables automatic_https
# ---------------------------------------------------------------------------

class TestTLSModeOff:
    def test_automatic_https_disabled(self) -> None:
        doc = _doc(tls_mode="off")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert server.get("automatic_https", {}).get("disable") is True

    def test_tls_stanza_empty(self) -> None:
        doc = _doc(tls_mode="off")
        assert _tls(doc) == {}


# ---------------------------------------------------------------------------
# TLS mode 'internal'
# ---------------------------------------------------------------------------

class TestTLSModeInternal:
    def test_no_automatic_https_key(self) -> None:
        doc = _doc(tls_mode="internal")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert "automatic_https" not in server

    def test_internal_issuer(self) -> None:
        doc = _doc(tls_mode="internal")
        policies = _tls(doc)["automation"]["policies"]
        issuers = [i for p in policies for i in p.get("issuers", [])]
        assert any(i.get("module") == "internal" for i in issuers)


# ---------------------------------------------------------------------------
# TLS mode 'tailscale'
# ---------------------------------------------------------------------------

class TestTLSModeTailscale:
    def test_tailscale_get_certificate(self) -> None:
        doc = _doc(tls_mode="tailscale")
        policies = _tls(doc)["automation"]["policies"]
        certs = [c for p in policies for c in p.get("get_certificate", [])]
        assert any(c.get("via") == "tailscale" for c in certs)

    def test_no_automatic_https_key(self) -> None:
        doc = _doc(tls_mode="tailscale")
        server = doc["apps"]["http"]["servers"]["ga-main"]
        assert "automatic_https" not in server


# ---------------------------------------------------------------------------
# (d) TLS mode 'acme' includes domain in TLS policy
# ---------------------------------------------------------------------------

class TestTLSModeAcme:
    def test_acme_domain_in_subjects(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com")
        policies = _tls(doc)["automation"]["policies"]
        subjects = [s for p in policies for s in p.get("subjects", [])]
        assert "example.com" in subjects

    def test_acme_issuer_module(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com")
        policies = _tls(doc)["automation"]["policies"]
        issuers = [i for p in policies for i in p.get("issuers", [])]
        assert any(i.get("module") == "acme" for i in issuers)


# ---------------------------------------------------------------------------
# (b) With API key — 401 handler present
# ---------------------------------------------------------------------------

class TestWithApiKey:
    def test_reject_route_present(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        assert "ga-mcp-files-reject" in _route_ids(doc)

    def test_reject_route_returns_401(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-mcp-files-reject")
        assert route is not None
        status = route["handle"][0]["status_code"]
        assert status == 401

    def test_mcp_route_bearer_gated(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        match = route["match"][0]
        # Must have a header match (bearer gate)
        assert "header" in match
        assert "Authorization" in match["header"]

    def test_files_presigned_route_present(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        assert "ga-transport-files-presigned" in _route_ids(doc)

    def test_radar_route_has_handle_response(self) -> None:
        """Session-gated radar route uses reverse_proxy handle_response."""
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        # First handler must be a reverse_proxy with handle_response
        handler = route["handle"][0]
        assert handler.get("handler") == "reverse_proxy"
        assert "handle_response" in handler


    def test_crew_dashboard_route_bearer_gated(self) -> None:
        doc = _doc(ga_api_key="mysecret")
        route = _find_route(doc, "ga-transport-crew-dashboard")
        assert route is not None
        match = route["match"][0]
        assert match["path"] == ["/crews/*/dashboard"]
        assert sorted(match["method"]) == ["DELETE", "POST"]
        assert "Authorization" in match["header"]
        assert route["handle"][0]["upstreams"] == [{"dial": "ga-transport:64057"}]

    def test_crew_dashboard_unauthed_hits_401(self) -> None:
        """Requests without the bearer fall through to the 401 reject route."""
        doc = _doc(ga_api_key="mysecret")
        ids = _route_ids(doc)
        reject = _find_route(doc, "ga-mcp-files-reject")
        assert "/crews/*/dashboard" in reject["match"][0]["path"]
        assert ids.index("ga-transport-crew-dashboard") < ids.index("ga-mcp-files-reject")


class TestAdminSocket:
    def test_admin_api_uses_owner_only_unix_socket(self) -> None:
        doc = _doc()
        assert doc["admin"]["listen"] == "unix//run/ga-portal-admin/admin.sock|0600"
        assert "2019" not in doc["admin"]["listen"]


# ---------------------------------------------------------------------------
# (c) Without API key — no 401 handler present
# ---------------------------------------------------------------------------

class TestWithoutApiKey:
    def test_no_reject_route(self) -> None:
        doc = _doc(ga_api_key="")
        assert "ga-mcp-files-reject" not in _route_ids(doc)

    def test_mcp_route_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        match = route["match"][0]
        # No bearer header gate
        assert "header" not in match

    def test_mcp_route_keeps_transport_upstream(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        assert route is not None
        assert route["handle"][0]["upstreams"] == [
            {"dial": "ga-transport:64057"}
        ]

    def test_no_files_presigned_route(self) -> None:
        doc = _doc(ga_api_key="")
        assert "ga-transport-files-presigned" not in _route_ids(doc)

    def test_crew_dashboard_route_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-crew-dashboard")
        assert route is not None
        match = route["match"][0]
        assert match["path"] == ["/crews/*/dashboard"]
        assert sorted(match["method"]) == ["DELETE", "POST"]
        assert "header" not in match

    def test_radar_route_is_passthrough(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        # Passthrough: single handler, no handle_response
        assert len(route["handle"]) == 1
        handler = route["handle"][0]
        assert handler.get("handler") == "reverse_proxy"
        assert "handle_response" not in handler


# ---------------------------------------------------------------------------
# Misc route always present
# ---------------------------------------------------------------------------

class TestMiscRoute:
    def test_misc_route_present(self) -> None:
        doc = _doc()
        assert "ga-transport-misc" in _route_ids(doc)

    def test_misc_route_matches_health_and_dashboard(self) -> None:
        doc = _doc()
        route = _find_route(doc, "ga-transport-misc")
        assert route is not None
        paths = route["match"][0]["path"]
        assert "/health" in paths
        assert "/dashboard/*" in paths

    def test_misc_route_is_last(self) -> None:
        doc = _doc()
        ids = _route_ids(doc)
        assert ids[-1] == "ga-transport-misc"


# ---------------------------------------------------------------------------
# Portal-token header on upstreams
# ---------------------------------------------------------------------------

class TestPortalTokenHeader:
    def test_mcp_route_injects_transport_token(self) -> None:
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-transport-mcp")
        handler = route["handle"][0]
        token_header = handler["headers"]["request"]["set"].get(
            "X-Transport-Token", []
        )
        assert any("ga-transport-secret" in t for t in token_header)


# ---------------------------------------------------------------------------
# JSON serialisability
# ---------------------------------------------------------------------------

class TestJSONSerialisation:
    def test_output_is_json_serialisable(self) -> None:
        doc = _doc(tls_mode="acme", acme_domain="example.com", ga_api_key="key")
        # Must not raise
        json.dumps(doc, indent=2)


# ---------------------------------------------------------------------------
# Radar mailbox-subject route (TRN-370)
# ---------------------------------------------------------------------------

class TestRadarMailSubjectsRoute:
    """GET /api/crews/{id}/mail-subjects is reachable only through the Radar route."""

    MAIL_PATH = "/api/crews/alpha/mail-subjects"

    def test_gated_route_matches_mail_subjects_path(self) -> None:
        import fnmatch
        doc = _doc(ga_api_key="secret")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        patterns = route["match"][0]["path"]
        assert any(fnmatch.fnmatchcase(self.MAIL_PATH, p) for p in patterns)

    def test_gated_route_keeps_forward_auth_in_front_of_radar(self) -> None:
        doc = _doc(ga_api_key="secret")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        # The first handler is the forward-auth proxy to transport; the Radar
        # upstream is only reached after the session check passes.
        forward_auth = route["handle"][0]
        assert forward_auth["upstreams"] == [{"dial": "ga-transport:64057"}]
        assert forward_auth["rewrite"]["uri"] == "/dashboard/auth"
        assert route["handle"][1]["upstreams"] == [{"dial": "ga-radar:8080"}]

    def test_passthrough_route_matches_mail_subjects_path(self) -> None:
        import fnmatch
        doc = _doc(ga_api_key="")
        route = _find_route(doc, "ga-radar")
        assert route is not None
        patterns = route["match"][0]["path"]
        assert any(fnmatch.fnmatchcase(self.MAIL_PATH, p) for p in patterns)


# ---------------------------------------------------------------------------
# Radar auth-refresh route (TRN-367): the POST stays behind the session gate
# ---------------------------------------------------------------------------

REFRESH_PATH = "/api/crews/alpha/auth/refresh"
LOGIN_REDIRECT = "/dashboard/login?next=" + REFRESH_PATH


def _route_matches(route: dict, method: str, path: str, headers: dict, query: dict) -> bool:
    """Caddy route matching for the matchers the generated config uses.

    Matchers within a route are alternatives (OR); keys within one matcher must
    all hold (AND). ``header`` and ``query`` matchers compare a secret file or a
    signature the test never supplies, so they hold only when the request carries
    the named field at all (callers here send none).
    """
    import fnmatch

    for matcher in route.get("match", [{}]):
        if "path" in matcher and not any(fnmatch.fnmatchcase(path, p) for p in matcher["path"]):
            continue
        if "method" in matcher and method not in matcher["method"]:
            continue
        if any(name not in headers for name in matcher.get("header", {})):
            continue
        if any(name not in query for name in matcher.get("query", {})):
            continue
        return True
    return False


def _serve(doc: dict, method: str, path: str, *, auth_status: int, uri: str | None = None):
    """Walk the main server's routes as Caddy would for one request.

    Returns ``(route_id, upstreams_reached, response)``. ``auth_status`` is what
    the forward-auth sub-request (``GET /dashboard/auth``) returns. A
    ``reverse_proxy`` with ``handle_response`` is the forward-auth step: a
    response class with a ``vars`` route lets the request continue, one with a
    ``static_response`` answers the client instead, and a status matching neither
    is sent to the client as the auth upstream's own response, so the request
    never continues.
    """
    uri = uri or path
    for route in _routes(doc):
        if not _route_matches(route, method, path, {}, {}):
            continue
        reached: list[str] = []
        for handler in route["handle"]:
            if handler["handler"] == "static_response":
                return route["@id"], reached, {"status": handler["status_code"]}
            assert handler["handler"] == "reverse_proxy", handler["handler"]
            reached.append(handler["upstreams"][0]["dial"] + handler.get("rewrite", {}).get("uri", uri))
            if "handle_response" not in handler:
                return route["@id"], reached, {"proxied": True}
            verdict = None
            for branch in handler["handle_response"]:
                if auth_status // 100 in branch["match"]["status_code"]:
                    verdict = branch["routes"][0]["handle"][0]
                    break
            if verdict is None:
                return route["@id"], reached, {"status": auth_status, "from_auth_upstream": True}
            if verdict["handler"] == "static_response":
                location = verdict["headers"]["Location"][0].replace("{http.request.uri}", uri)
                return route["@id"], reached, {"status": verdict["status_code"], "location": location}
            assert verdict["handler"] == "vars"  # 2xx: carry on to the next handler
        raise AssertionError(f"route {route['@id']} has no terminal handler")
    return None, [], {"status": 200, "unhandled": True}


class TestRadarAuthRefreshGate:
    """POST /api/crews/{id}/auth/refresh goes through forward_auth before Radar."""

    FORWARD_AUTH = "ga-transport:64057/dashboard/auth"
    RADAR = "ga-radar:8080" + REFRESH_PATH

    def _doc(self) -> dict:
        return _doc(ga_api_key="secret")

    def test_first_matching_route_for_the_post_is_the_radar_route(self) -> None:
        route_id, _reached, _response = _serve(self._doc(), "POST", REFRESH_PATH, auth_status=200)
        assert route_id == "ga-radar"

    def test_no_earlier_route_claims_the_refresh_path_for_any_method(self) -> None:
        doc = self._doc()
        for method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
            for route in _routes(doc):
                if route["@id"] == "ga-radar":
                    break
                assert not _route_matches(route, method, REFRESH_PATH, {}, {}), (method, route["@id"])

    def test_radar_matcher_is_not_limited_to_get(self) -> None:
        # A method constraint would either skip the gate for POST or send it elsewhere.
        for gated in (True, False):
            route = _find_route(_doc(ga_api_key="secret" if gated else ""), "ga-radar")
            for matcher in route["match"]:
                assert "method" not in matcher
            for method in ("GET", "POST"):
                assert _route_matches(route, method, REFRESH_PATH, {}, {})

    def test_valid_session_reaches_radar_after_the_auth_check(self) -> None:
        _id, reached, response = _serve(self._doc(), "POST", REFRESH_PATH, auth_status=200)
        assert reached == [self.FORWARD_AUTH, self.RADAR]
        assert response == {"proxied": True}

    def test_any_2xx_auth_answer_lets_the_request_continue(self) -> None:
        for status in (200, 204):
            _id, reached, _response = _serve(self._doc(), "POST", REFRESH_PATH, auth_status=status)
            assert reached[-1] == self.RADAR, status

    def test_invalid_session_is_redirected_to_login_and_never_reaches_radar(self) -> None:
        for status in (400, 401, 403, 404, 429):
            _id, reached, response = _serve(self._doc(), "POST", REFRESH_PATH, auth_status=status)
            assert reached == [self.FORWARD_AUTH], status
            assert response == {"status": 302, "location": LOGIN_REDIRECT}, status

    def test_unexpected_auth_answers_fail_closed(self) -> None:
        # A broken or unreachable auth upstream must not let the request through.
        for status in (301, 302, 500, 502, 503, 504):
            _id, reached, response = _serve(self._doc(), "POST", REFRESH_PATH, auth_status=status)
            assert self.RADAR not in reached, status
            assert response["status"] == status and response["from_auth_upstream"], status

    def test_post_is_gated_exactly_like_get(self) -> None:
        for auth_status in (200, 401, 502):
            results = {m: _serve(self._doc(), m, REFRESH_PATH, auth_status=auth_status)
                       for m in ("GET", "POST", "PUT", "DELETE")}
            assert len({repr(r) for r in results.values()}) == 1, (auth_status, results)

    def test_radar_is_only_ever_the_second_handler(self) -> None:
        route = _find_route(self._doc(), "ga-radar")
        handlers = route["handle"]
        assert [h["upstreams"] for h in handlers] == [
            [{"dial": "ga-transport:64057"}], [{"dial": "ga-radar:8080"}],
        ]
        assert "handle_response" in handlers[0] and "handle_response" not in handlers[1]

    def test_the_get_rewrite_applies_to_the_auth_request_only(self) -> None:
        # Radar must see the browser's POST: the rewrite to GET belongs to the first handler.
        gate, radar = _find_route(self._doc(), "ga-radar")["handle"]
        assert gate["rewrite"] == {"method": "GET", "uri": "/dashboard/auth"}
        assert "rewrite" not in radar

    def test_auth_request_reports_the_original_method_and_uri(self) -> None:
        gate = _find_route(self._doc(), "ga-radar")["handle"][0]
        headers = gate["headers"]["request"]["set"]
        assert headers["X-Forwarded-Method"] == ["{http.request.method}"]
        assert headers["X-Forwarded-Uri"] == ["{http.request.uri}"]
        assert any("ga-transport-secret" in v for v in headers["X-Transport-Token"])

    def test_login_redirect_keeps_the_requested_uri(self) -> None:
        branch = _find_route(self._doc(), "ga-radar")["handle"][0]["handle_response"][1]
        assert branch["match"] == {"status_code": [4]}
        redirect = branch["routes"][0]["handle"][0]
        assert redirect["status_code"] == 302
        assert redirect["headers"]["Location"] == ["/dashboard/login?next={http.request.uri}"]

    def test_radar_upstream_receives_host_and_origin_unchanged(self) -> None:
        # Radar's same-origin check compares the browser's Origin with the Host it
        # was sent; overriding Host or dropping Origin would reject every refresh.
        for gated in (True, False):
            route = _find_route(_doc(ga_api_key="secret" if gated else ""), "ga-radar")
            radar = route["handle"][-1]
            assert radar["upstreams"] == [{"dial": "ga-radar:8080"}]
            ops = radar["headers"]["request"]
            assert set(ops["set"]) == {"X-Transport-Token"}
            assert "delete" not in ops and "add" not in ops and "replace" not in ops
            assert "rewrite" not in radar

    def test_route_does_not_depend_on_the_tls_mode(self) -> None:
        reference = _find_route(_doc(ga_api_key="secret", tls_mode="off"), "ga-radar")
        for mode, extra in (("internal", {}), ("tailscale", {}), ("acme", {"acme_domain": "example.com"})):
            assert _find_route(_doc(ga_api_key="secret", tls_mode=mode, **extra), "ga-radar") == reference

    def test_no_other_route_exposes_a_mutating_radar_path(self) -> None:
        # Only the gated Radar route is reachable for /api/crews/*; the transport's own
        # routes must not shadow it for any method.
        for method in ("POST", "PUT", "DELETE"):
            for path in ("/api/crews/alpha/auth/refresh", "/api/crews/alpha/agents", "/api/crews"):
                route_id, _reached, _response = _serve(self._doc(), method, path, auth_status=401)
                assert route_id == "ga-radar", (method, path)


class TestRadarAuthRefreshGateAgainstTheRealSessionCheck:
    """The gate's verdict comes from DashboardGate.handle_auth, which reads only the session."""

    URI = REFRESH_PATH

    def _gate(self, **kwargs):
        from transport.dashboard import DashboardGate
        return DashboardGate(
            session_ttl_secs=kwargs.pop("session_ttl_secs", 3600),
            api_key=kwargs.pop("api_key", "gate-key-for-tests"),
            external_url="http://localhost",
            **kwargs,
        )

    @staticmethod
    def _auth_status(gate, *, cookie: str | None, forwarded_method: str) -> int:
        """Status of the forward-auth sub-request Caddy sends for a request."""
        import asyncio
        from starlette.requests import Request

        headers = [
            (b"x-forwarded-method", forwarded_method.encode()),
            (b"x-forwarded-uri", REFRESH_PATH.encode()),
            (b"x-transport-token", b"portal-secret"),
        ]
        if cookie is not None:
            headers.append((b"cookie", f"gs_session={cookie}".encode()))
        scope = {"type": "http", "method": "GET", "path": "/dashboard/auth", "query_string": b"",
                 "headers": headers, "client": ("203.0.113.5", 4242)}
        return asyncio.run(gate.handle_auth(Request(scope))).status_code

    def _reaches_radar(self, gate, *, cookie, method="POST") -> bool:
        status = self._auth_status(gate, cookie=cookie, forwarded_method=method)
        _id, reached, _response = _serve(
            _doc(ga_api_key="secret"), method, REFRESH_PATH, auth_status=status,
        )
        return any(step.startswith("ga-radar:8080") for step in reached)

    def test_valid_session_reaches_radar(self) -> None:
        gate = self._gate()
        assert self._reaches_radar(gate, cookie=gate._sessions.issue())

    def test_missing_session_never_reaches_radar(self) -> None:
        assert not self._reaches_radar(self._gate(), cookie=None)

    def test_forged_or_malformed_session_never_reaches_radar(self) -> None:
        gate = self._gate()
        for cookie in ("forged", "A" * 43, "", "../../etc/passwd", gate._sessions.issue() + "x"):
            assert not self._reaches_radar(gate, cookie=cookie), cookie

    def test_expired_session_never_reaches_radar(self) -> None:
        import time
        gate = self._gate(session_ttl_secs=3600)
        assert not self._reaches_radar(gate, cookie=gate._sessions.issue(now=time.time() - 4000))

    def test_revoked_session_never_reaches_radar(self) -> None:
        gate = self._gate()
        token = gate._sessions.issue()
        assert self._reaches_radar(gate, cookie=token)
        gate._sessions.revoke(token)
        assert not self._reaches_radar(gate, cookie=token)

    def test_gate_verdict_ignores_the_forwarded_method(self) -> None:
        # This is why the session gate alone cannot protect a mutating request,
        # and why Radar adds its own same-origin check on the POST.
        gate = self._gate()
        token = gate._sessions.issue()
        for method in ("GET", "POST", "PUT", "DELETE"):
            assert self._auth_status(gate, cookie=token, forwarded_method=method) == 200
            assert self._auth_status(gate, cookie=None, forwarded_method=method) == 401

    def test_two_session_cookies_are_refused(self) -> None:
        import asyncio
        from starlette.requests import Request

        gate = self._gate()
        token = gate._sessions.issue()
        scope = {"type": "http", "method": "GET", "path": "/dashboard/auth", "query_string": b"",
                 "headers": [(b"cookie", f"gs_session={token}; gs_session={token}".encode())]}
        assert asyncio.run(gate.handle_auth(Request(scope))).status_code == 401


class TestRadarAuthRefreshWithoutApiKey:
    """No API key (Tailscale-gated install): no session gate, the POST goes straight to Radar."""

    def test_post_reaches_radar_without_an_auth_check(self) -> None:
        route_id, reached, response = _serve(_doc(ga_api_key=""), "POST", REFRESH_PATH, auth_status=401)
        assert route_id == "ga-radar"
        assert reached == ["ga-radar:8080" + REFRESH_PATH]
        assert response == {"proxied": True}

    def test_no_forward_auth_handler_exists(self) -> None:
        route = _find_route(_doc(ga_api_key=""), "ga-radar")
        assert len(route["handle"]) == 1
        assert "handle_response" not in route["handle"][0]
        assert "rewrite" not in route["handle"][0]
