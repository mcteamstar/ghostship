"""HTTP-surface tests for the crew auth refresh routes (TRN-367).

Covers ``POST /crews/{crew_id}/auth/refresh`` (bearer-protected operator route)
and ``POST /internal/crews/{crew_id}/auth/refresh`` (transport-secret route used
by Radar):

- every defined outcome is HTTP 200 with the outcome in ``status``, and both
  routes return the same body for the same crew;
- only an unknown crew is 404, and nothing is refreshed for it;
- bearer, ``X-Transport-Token`` and browser ``Origin`` rejections happen before
  the refresh operation runs;
- both routes are registered by ``server.py`` and listed in the OpenAPI schema.

The real handlers run behind the real ``BearerAuthMiddleware`` and
``TransportSecretMiddleware``; only the refresh operation itself is replaced
(it is covered in ``test_auth_refresh.py``).
"""

from __future__ import annotations

import ast
import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from transport import server
from transport.auth import BearerAuthMiddleware, TransportSecretMiddleware
from transport.auth_refresh import CrewNotFound, OUTCOMES
from transport.openapi import generate_schema

OPERATOR_ROUTE = ("POST", "/crews/*/auth/refresh")
INTERNAL_ROUTE = ("POST", "/internal/crews/*/auth/refresh")
OPERATOR_PATH = "/crews/alpha/auth/refresh"
INTERNAL_PATH = "/internal/crews/alpha/auth/refresh"
API_KEY = "operator-bearer-key"
TRANSPORT_TOKEN = "portal-transport-secret"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _outcome(status: str, crew_id: str = "alpha") -> dict:
    return {
        "status": status,
        "crew_id": crew_id,
        "backend": "kiro",
        "profile": "default",
        "message": f"message for {status}",
    }


def _stack(*, api_key: str = API_KEY, transport_secret: str = TRANSPORT_TOKEN):
    """The real middleware stack with the server's real refresh handlers registered."""
    async def _inner(scope, receive, send):
        raise AssertionError("the MCP app must not receive a refresh route")

    bearer = BearerAuthMiddleware(
        _inner,
        api_key=api_key,
        routes={OPERATOR_ROUTE: server._handle_crew_auth_refresh_post},
        public_routes={INTERNAL_ROUTE: server._handle_internal_crew_auth_refresh_post},
    )
    return TransportSecretMiddleware(bearer, transport_secret=transport_secret)


def _call(
    app,
    method: str,
    path: str,
    headers: dict[str, str] | None = None,
    *,
    body: bytes = b"",
    query: bytes = b"",
) -> tuple[int, bytes, dict]:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query,
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("203.0.113.9", 4000),
    }
    messages: list[dict] = []

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def _send(message):
        messages.append(message)

    _run(app(scope, _receive, _send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    response_headers = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return start["status"], body, response_headers


def _operator(app, headers=None, method="POST", path=OPERATOR_PATH):
    merged = {"authorization": f"Bearer {API_KEY}", "x-transport-token": TRANSPORT_TOKEN}
    merged.update(headers or {})
    return _call(app, method, path, merged)


def _internal(app, headers=None, path=INTERNAL_PATH):
    merged = {"x-transport-token": TRANSPORT_TOKEN}
    merged.update(headers or {})
    return _call(app, "POST", path, merged)


class _RefreshPatch:
    """Replaces the refresh operation and records the crew ids it was asked to refresh."""

    def __init__(self, result=None, error: BaseException | None = None):
        self.calls: list[str] = []
        self._result, self._error = result, error

    def __call__(self, crew_id: str) -> dict:
        self.calls.append(crew_id)
        if self._error is not None:
            raise self._error
        return self._result(crew_id) if callable(self._result) else self._result

    def __enter__(self):
        self._patcher = patch.object(server._auth_refresh, "refresh_crew_auth", self)
        self._patcher.start()
        return self

    def __exit__(self, *exc):
        self._patcher.stop()
        return False


class TestOutcomesAreHttp200(unittest.TestCase):
    """Every defined outcome is a 200 carrying ``status``; both routes agree."""

    def test_every_outcome_is_200_on_both_routes(self):
        app = _stack()
        for status in OUTCOMES:
            with self.subTest(status=status):
                with _RefreshPatch(_outcome(status)) as operation:
                    operator_code, operator_body, operator_headers = _operator(app)
                    internal_code, internal_body, _ = _internal(app)
                self.assertEqual((operator_code, internal_code), (200, 200))
                self.assertEqual(json.loads(operator_body)["status"], status)
                self.assertEqual(json.loads(operator_body), json.loads(internal_body))
                self.assertIn("application/json", operator_headers["content-type"])
                self.assertEqual(operation.calls, ["alpha", "alpha"])

    def test_outcome_set_matches_the_documented_six(self):
        self.assertEqual(
            set(OUTCOMES),
            {"refreshed", "pending_on_wake", "current", "recreate_required",
             "credential_missing", "refresh_failed"},
        )

    def test_crew_id_comes_from_the_path_only(self):
        app = _stack()
        with _RefreshPatch(lambda crew_id: _outcome("refreshed", crew_id)) as operation:
            _operator(app, path="/crews/bravo/auth/refresh")
            _internal(app, path="/internal/crews/charlie/auth/refresh")
        self.assertEqual(operation.calls, ["bravo", "charlie"])

    def test_request_body_and_query_are_not_a_credential_channel(self):
        # The operation's only input is the crew id from the path, so a caller can
        # neither supply a credential nor pick a different backend or profile.
        import inspect
        from transport.auth_refresh import refresh_crew_auth
        self.assertEqual(list(inspect.signature(refresh_crew_auth).parameters), ["crew_id"])

        app = _stack()
        hostile_body = json.dumps({
            "credential": "caller-supplied-secret", "backend": "codex", "profile": "other",
        }).encode()
        hostile_query = b"backend=codex&profile=other&secret=caller-supplied-secret"
        for call, extra in ((_operator, {}), (_internal, {})):
            with self.subTest(route=call.__name__), _RefreshPatch(_outcome("refreshed")) as operation:
                headers = {"content-type": "application/json", "content-length": str(len(hostile_body))}
                merged = {"x-transport-token": TRANSPORT_TOKEN, **headers}
                if call is _operator:
                    merged["authorization"] = f"Bearer {API_KEY}"
                path = OPERATOR_PATH if call is _operator else INTERNAL_PATH
                code, body, _ = _call(app, "POST", path, merged, body=hostile_body, query=hostile_query)
                self.assertEqual(code, 200)
                self.assertEqual(operation.calls, ["alpha"])
                self.assertNotIn(b"caller-supplied-secret", body)
                self.assertEqual(json.loads(body), _outcome("refreshed"))


class TestUnknownCrew(unittest.TestCase):

    def test_unknown_crew_is_404_on_both_routes(self):
        app = _stack()
        with _RefreshPatch(error=CrewNotFound("alpha")) as operation:
            for call in (_operator, _internal):
                with self.subTest(route=call.__name__):
                    code, body, _ = call(app)
                    self.assertEqual(code, 404)
                    self.assertEqual(json.loads(body), {"error": "crew 'alpha' not found"})
        self.assertEqual(operation.calls, ["alpha", "alpha"])

    def test_unknown_crew_through_the_real_operation_changes_nothing(self):
        app = _stack()
        with patch("transport.auth_refresh._get_crew", side_effect=KeyError("alpha")), \
             patch("transport.auth_refresh._login._cred_store") as store, \
             patch("transport.auth_refresh._get_podman") as podman:
            for call in (_operator, _internal):
                self.assertEqual(call(app)[0], 404)
        store.get.assert_not_called()
        store.put.assert_not_called()
        store.delete.assert_not_called()
        podman.assert_not_called()

    def test_unexpected_error_is_a_500_without_exception_text(self):
        app = _stack()
        with _RefreshPatch(error=RuntimeError("registry says secret-detail-1234")):
            with self.assertLogs(server.logger, level="ERROR"):
                for call in (_operator, _internal):
                    code, body, _ = call(app)
                    self.assertEqual(code, 500)
                    self.assertEqual(json.loads(body), {"error": "crew auth refresh failed"})
                    self.assertNotIn(b"secret-detail-1234", body)


class TestOperatorRouteAuth(unittest.TestCase):

    def test_missing_bearer_is_rejected_before_any_refresh(self):
        app = _stack()
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, body, headers = _call(app, "POST", OPERATOR_PATH, {"x-transport-token": TRANSPORT_TOKEN})
        self.assertEqual(code, 401)
        self.assertEqual(headers["www-authenticate"], "Bearer")
        self.assertEqual(operation.calls, [])
        self.assertNotIn(b"refreshed", body)

    def test_wrong_and_malformed_bearer_are_rejected(self):
        app = _stack()
        for authorization in ("Bearer wrong-key", "Token abc", "Bearer", API_KEY):
            with self.subTest(authorization=authorization), _RefreshPatch(_outcome("refreshed")) as operation:
                code, _, _ = _operator(app, {"authorization": authorization})
                self.assertEqual(code, 401)
                self.assertEqual(operation.calls, [])

    def test_transport_token_alone_does_not_authorise_the_operator_route(self):
        # The internal secret is for portside callers; it must not stand in for the operator key.
        app = _stack()
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _call(app, "POST", OPERATOR_PATH, {"x-transport-token": TRANSPORT_TOKEN})
        self.assertEqual(code, 401)
        self.assertEqual(operation.calls, [])

    def test_valid_bearer_reaches_the_operation(self):
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _operator(_stack())
        self.assertEqual(code, 200)
        self.assertEqual(operation.calls, ["alpha"])

    def test_browser_origin_is_rejected_before_any_refresh(self):
        app = _stack()
        for origin in ("https://evil.example", "http://localhost:64057", "null", ""):
            with self.subTest(origin=origin), _RefreshPatch(_outcome("refreshed")) as operation:
                code, body, _ = _operator(app, {"origin": origin})
                self.assertEqual(code, 403)
                self.assertEqual(json.loads(body), {"error": "browser requests are not accepted on this endpoint"})
                self.assertEqual(operation.calls, [])

    def test_origin_is_rejected_even_with_a_valid_bearer_and_no_api_key_configured(self):
        app = _stack(api_key="")
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _call(app, "POST", OPERATOR_PATH,
                               {"x-transport-token": TRANSPORT_TOKEN, "origin": "https://evil.example"})
        self.assertEqual(code, 403)
        self.assertEqual(operation.calls, [])

    def test_no_api_key_configured_serves_the_route_without_a_bearer(self):
        app = _stack(api_key="")
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, body, _ = _call(app, "POST", OPERATOR_PATH, {"x-transport-token": TRANSPORT_TOKEN})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "refreshed")
        self.assertEqual(operation.calls, ["alpha"])

    def test_other_methods_are_405_and_never_reach_the_mcp_app(self):
        for api_key in (API_KEY, ""):
            app = _stack(api_key=api_key)
            for method in ("GET", "PUT", "DELETE", "PATCH"):
                with self.subTest(method=method, keyed=bool(api_key)), _RefreshPatch(_outcome("refreshed")) as operation:
                    code, _, headers = _operator(app, method=method)
                    self.assertEqual(code, 405)
                    self.assertEqual(headers["allow"], "POST")
                    self.assertEqual(operation.calls, [])

    def test_unauthenticated_other_method_is_401_not_405(self):
        # The bearer gate comes first, so an unauthenticated caller learns nothing about the route.
        code, _, _ = _call(_stack(), "GET", OPERATOR_PATH, {"x-transport-token": TRANSPORT_TOKEN})
        self.assertEqual(code, 401)

    def test_paths_that_only_resemble_the_route_are_not_dispatched_to_it(self):
        app = _stack()
        for path in ("/crews/alpha/auth", "/crews/alpha/auth/refresh/extra", "/crews/auth/refresh",
                     "/crews/alpha/auth/refreshx", "/crews/alpha/api/auth/refresh"):
            with self.subTest(path=path), _RefreshPatch(_outcome("refreshed")) as operation:
                with self.assertRaises(AssertionError):  # falls through to the inner MCP app stub
                    _operator(app, path=path)
                self.assertEqual(operation.calls, [])

    def test_failed_bearer_attempts_are_throttled_like_other_operator_routes(self):
        app = _stack()
        codes = [
            _call(app, "POST", OPERATOR_PATH,
                  {"x-transport-token": TRANSPORT_TOKEN, "authorization": "Bearer wrong"})[0]
            for _ in range(12)
        ]
        self.assertEqual(codes[0], 401)
        self.assertIn(429, codes)


class TestInternalRouteAuth(unittest.TestCase):

    def test_missing_transport_token_is_401_and_performs_no_refresh(self):
        app = _stack()
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, body, headers = _call(app, "POST", INTERNAL_PATH)
        self.assertEqual(code, 401)
        self.assertEqual(headers["www-authenticate"], "Transport-Token")
        self.assertEqual(operation.calls, [])
        self.assertNotIn(b"refreshed", body)

    def test_wrong_transport_token_is_401(self):
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _internal(_stack(), {"x-transport-token": "wrong"})
        self.assertEqual(code, 401)
        self.assertEqual(operation.calls, [])

    def test_duplicate_transport_tokens_are_401(self):
        app = _stack()
        scope_headers = [(b"x-transport-token", TRANSPORT_TOKEN.encode()), (b"x-transport-token", TRANSPORT_TOKEN.encode())]
        messages: list[dict] = []
        scope = {"type": "http", "method": "POST", "path": INTERNAL_PATH, "query_string": b"", "headers": scope_headers}

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(message):
            messages.append(message)

        with _RefreshPatch(_outcome("refreshed")) as operation:
            _run(app(scope, _receive, _send))
        self.assertEqual(messages[0]["status"], 401)
        self.assertEqual(operation.calls, [])

    def test_valid_transport_token_needs_no_bearer_key(self):
        with _RefreshPatch(_outcome("pending_on_wake")) as operation:
            code, body, _ = _internal(_stack())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["status"], "pending_on_wake")
        self.assertEqual(operation.calls, ["alpha"])

    def test_bearer_key_does_not_replace_the_transport_token(self):
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _call(_stack(), "POST", INTERNAL_PATH, {"authorization": f"Bearer {API_KEY}"})
        self.assertEqual(code, 401)
        self.assertEqual(operation.calls, [])

    def test_other_methods_are_not_served_by_the_internal_route(self):
        # Only POST is registered as a transport-secret route; any other method
        # falls to the bearer-protected path, which refuses it without the key.
        app = _stack()
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            with self.subTest(method=method), _RefreshPatch(_outcome("refreshed")) as operation:
                code, _, _ = _call(app, method, INTERNAL_PATH, {"x-transport-token": TRANSPORT_TOKEN})
                self.assertEqual(code, 401)
                self.assertEqual(operation.calls, [])

    def test_internal_route_ignores_a_browser_origin_header_it_never_receives_from_radar(self):
        # Radar builds its own request, so no Origin arrives; the secret is the gate.
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _internal(_stack(), {"origin": "https://portal.example"})
        self.assertEqual(code, 200)
        self.assertEqual(operation.calls, ["alpha"])

    def test_no_transport_secret_configured_is_pass_through_like_other_internal_routes(self):
        with _RefreshPatch(_outcome("refreshed")) as operation:
            code, _, _ = _call(_stack(transport_secret=""), "POST", INTERNAL_PATH)
        self.assertEqual(code, 200)
        self.assertEqual(operation.calls, ["alpha"])


class TestRefreshResultContainsNoSecret(unittest.TestCase):

    def test_response_body_is_exactly_the_operation_result(self):
        result = _outcome("recreate_required")
        with _RefreshPatch(result):
            for call in (_operator, _internal):
                self.assertEqual(json.loads(call(_stack())[1]), result)


# ── Registration in server.py and the OpenAPI schema ─────────────────────────


def _capture_registered_tables() -> dict:
    """Run server.py's real ``__main__`` block and capture the tables it registers."""
    captured: dict = {}

    class _Registry:
        _reg = {"crews": {}}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class _Thread:
        def __init__(self, *_args, **_kwargs):
            pass

        def start(self):
            pass

    def _bearer(app, **kwargs):
        captured["bearer"] = kwargs
        return app

    def _generate_schema(**kwargs):
        captured["schema_args"] = kwargs
        return {"paths": {}}

    def _run_main(coro):
        coro.close()

    parsed = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
    entrypoint = next(
        node for node in parsed.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
    )
    config = server.Config(ga_transport_bind="0.0.0.0", ga_portal_host="127.0.0.1")
    namespace = vars(server).copy()
    namespace.update({
        "__name__": "__main__",
        "cfg": config,
        "GA_API_KEY": API_KEY,
        "_warn_inert_backend_settings": lambda: None,
        "_reconcile_registry": lambda: None,
        "_validate_academy": lambda: [],
        "registry": _Registry(),
        "_dashboard_ports_in_use": set(),
        "threading": SimpleNamespace(Thread=_Thread),
        "mcp": SimpleNamespace(streamable_http_app=lambda **_kwargs: object()),
        "_dashboard_gate": SimpleNamespace(
            handle_login_post=None, handle_logout_post=None, handle_auth=None, handle_login_get=None,
        ),
        "Starlette": lambda **_kwargs: object(),
        "_openapi": SimpleNamespace(generate_schema=_generate_schema, get_mcp_tools=lambda _mcp: []),
        "BearerAuthMiddleware": _bearer,
        "_build_rate_limiters": lambda: None,
        "SecurityHeadersMiddleware": lambda app, **_kwargs: app,
        "TransportSecretMiddleware": lambda app, **_kwargs: app,
        "uvicorn": SimpleNamespace(Config=lambda *_a, **_kw: object(), Server=lambda _config: object()),
        "asyncio": SimpleNamespace(run=_run_main),
    })
    with patch.object(server, "cfg", config):
        code = compile(ast.Module(body=[entrypoint], type_ignores=[]), server.__file__, "exec")
        exec(code, namespace)
    return captured


class TestRegistration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.captured = _capture_registered_tables()

    def test_operator_route_is_registered_as_a_bearer_route(self):
        routes = self.captured["bearer"]["routes"]
        self.assertIs(routes[OPERATOR_ROUTE], server._handle_crew_auth_refresh_post)
        self.assertNotIn(OPERATOR_ROUTE, self.captured["bearer"]["public_routes"])

    def test_internal_route_is_registered_as_a_transport_secret_route(self):
        public_routes = self.captured["bearer"]["public_routes"]
        self.assertIs(public_routes[INTERNAL_ROUTE], server._handle_internal_crew_auth_refresh_post)
        self.assertNotIn(INTERNAL_ROUTE, self.captured["bearer"]["routes"])

    def test_openapi_inputs_match_what_the_middleware_serves(self):
        args = self.captured["schema_args"]
        bearer = self.captured["bearer"]
        self.assertIn(OPERATOR_ROUTE, args["routes"])
        self.assertIn(INTERNAL_ROUTE, args["public_routes"])
        self.assertIs(args["routes"][OPERATOR_ROUTE], bearer["routes"][OPERATOR_ROUTE])
        self.assertIs(args["public_routes"][INTERNAL_ROUTE], bearer["public_routes"][INTERNAL_ROUTE])

    def _schema(self) -> dict:
        args = self.captured["schema_args"]
        return generate_schema(
            routes=args["routes"], public_routes=args["public_routes"],
            file_routes=args["file_routes"], mcp_tools=[], version="test",
        )

    def test_openapi_lists_the_operator_route_with_bearer_security(self):
        entry = self._schema()["paths"]["/crews/{crew_id}/auth/refresh"]["post"]
        self.assertEqual(entry["security"], [{"BearerAuth": []}])
        self.assertEqual(entry["tags"], ["auth"])
        self.assertIn("Refresh the credential", entry["summary"])
        self.assertIn("200", entry["responses"])

    def test_openapi_lists_the_internal_route_without_bearer_security(self):
        entry = self._schema()["paths"]["/internal/crews/{crew_id}/auth/refresh"]["post"]
        self.assertEqual(entry["security"], [])
        self.assertEqual(entry["tags"], ["auth"])
        self.assertIn("X-Transport-Token", entry["summary"])

    def test_openapi_uses_named_parameters_not_wildcards(self):
        paths = self._schema()["paths"]
        self.assertFalse([p for p in paths if "auth/refresh" in p and ("*" in p or "param" in p)])

    def test_both_routes_are_post_only(self):
        paths = self._schema()["paths"]
        self.assertEqual(set(paths["/crews/{crew_id}/auth/refresh"]), {"post"})
        self.assertEqual(set(paths["/internal/crews/{crew_id}/auth/refresh"]), {"post"})


if __name__ == "__main__":
    unittest.main()
