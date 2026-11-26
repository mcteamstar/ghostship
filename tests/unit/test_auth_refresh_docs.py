"""Docs-versus-implementation checks for the crew auth refresh feature (TRN-367).

The operator documentation names routes, outcomes, response fields, status codes
and session-lifetime estimates. These tests read docs/auth.md (and, for the
Radar half, docs/radar.md) and check each claim against the code that
implements it, so the docs cannot drift from the routes without a test failing.

The Radar page is a React app (radar/web). Its wording and wiring are read from
those sources here; the behaviour itself is exercised by the Vitest suite
(radar/web/test/app/refresh-auth.test.tsx), which the docs claims point at.
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.test_auth_refresh_routes import (
    API_KEY,
    OPERATOR_PATH,
    INTERNAL_PATH,
    CrewNotFound,
    _RefreshPatch,
    _call,
    _internal,
    _operator,
    _outcome,
    _stack,
)
from transport import auth_refresh, launcher

_REPO = Path(__file__).parents[2]
_AUTH_MD = (_REPO / "docs" / "auth.md").read_text(encoding="utf-8")
_RADAR_MD = (_REPO / "docs" / "radar.md").read_text(encoding="utf-8")
_ARCH_MD = (_REPO / "docs" / "architecture.md").read_text(encoding="utf-8")

OPERATOR_DOC_ROUTE = "POST /crews/{crew_id}/auth/refresh"
INTERNAL_DOC_ROUTE = "POST /internal/crews/{crew_id}/auth/refresh"


def _section(markdown: str, heading: str) -> str:
    """The text under ``heading`` (any level) up to the next heading of the same or higher level."""
    lines = markdown.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if re.match(r"#+ " + re.escape(heading) + r"\s*$", line)),
        None,
    )
    if start is None:
        raise AssertionError(f"docs heading not found: {heading!r}")
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        match = re.match(r"(#+) ", lines[i])
        if match and len(match.group(1)) <= level:
            end = i
            break
    return "\n".join(lines[start:end])


def _anchors(markdown: str) -> set[str]:
    """GitHub-style heading anchors for a markdown document."""
    found = set()
    for line in markdown.splitlines():
        match = re.match(r"#+ (.+?)\s*(\{#([\w-]+)\})?\s*$", line)
        if not match:
            continue
        found.add(match.group(3) or re.sub(r"[^\w\- ]", "", match.group(1).lower()).replace(" ", "-"))
    return found


def _table_first_column(section: str) -> list[str]:
    """First-column code spans of a markdown table's body rows (the header row is skipped)."""
    names = []
    for line in section.splitlines():
        match = re.match(r"^\| `([a-z_]+)` \|", line)
        if match and not line.startswith("| `status` | Meaning"):
            names.append(match.group(1))
    return names


class TestAuthDocsRoutesMatchTheImplementation:

    SECTION = _section(_AUTH_MD, "Refresh a crew's auth")

    def _registered(self) -> dict:
        from tests.unit.test_auth_refresh_routes import _capture_registered_tables
        return _capture_registered_tables()

    @staticmethod
    def _as_route_key(doc_route: str) -> tuple[str, str]:
        method, path = doc_route.split(" ", 1)
        return method, re.sub(r"\{[a-z_]+\}", "*", path)

    def test_both_documented_routes_are_registered_with_the_documented_auth(self):
        tables = self._registered()["bearer"]
        assert f"`{OPERATOR_DOC_ROUTE}`" in self.SECTION
        assert f"`{INTERNAL_DOC_ROUTE}`" in self.SECTION
        assert self._as_route_key(OPERATOR_DOC_ROUTE) in tables["routes"]            # bearer-protected
        assert self._as_route_key(INTERNAL_DOC_ROUTE) in tables["public_routes"]     # transport-secret only
        assert self._as_route_key(OPERATOR_DOC_ROUTE) not in tables["public_routes"]
        assert self._as_route_key(INTERNAL_DOC_ROUTE) not in tables["routes"]

    def test_no_other_refresh_route_is_documented(self):
        documented = set(re.findall(r"`(POST [^`]*auth/refresh)`", self.SECTION))
        assert documented == {OPERATOR_DOC_ROUTE, INTERNAL_DOC_ROUTE}

    def test_documented_curl_example_hits_the_operator_route_with_a_bearer_key(self):
        command = re.search(r"```bash\n(.*?)```", self.SECTION, re.S).group(1)
        assert "-X POST" in command
        assert 'Authorization: Bearer $GHOSTSHIP_API_KEY' in command
        path = re.search(r'"\$TRANSPORT_URL(/[^"]+)"', command).group(1)
        method, pattern = self._as_route_key(OPERATOR_DOC_ROUTE)
        assert fnmatch.fnmatchcase(path, pattern)
        assert "internal" not in path
        # The same request, built the way the example builds it, is served by the real stack.
        with _RefreshPatch(_outcome("refreshed", "my-crew")) as operation:
            code, body, _ = _call(
                _stack(), "POST", path,
                {"authorization": f"Bearer {API_KEY}", "x-transport-token": "portal-transport-secret"},
            )
        assert code == 200
        assert operation.calls == ["my-crew"]
        assert json.loads(body)["status"] == "refreshed"

    def test_the_curl_example_uses_the_documented_environment_names(self):
        # GHOSTSHIP_API_KEY and GHOSTSHIP_URL are what the CLI itself reads.
        cli = (_REPO / "ghostship").read_text(encoding="utf-8")
        assert "GHOSTSHIP_API_KEY" in cli and "GHOSTSHIP_URL" in cli

    def test_documented_status_codes_are_what_the_routes_return(self):
        section = self.SECTION
        app = _stack()
        with _RefreshPatch(_outcome("refreshed")):
            assert _operator(app, {"origin": "https://evil.example"})[0] == 403       # browser Origin
            assert _operator(app, method="PUT")[0] == 405                              # other methods
            assert _call(app, "POST", OPERATOR_PATH, {"x-transport-token": "portal-transport-secret"})[0] == 401
            assert _call(app, "POST", INTERNAL_PATH)[0] == 401                         # no transport token
            assert _operator(app)[0] == 200 and _internal(app)[0] == 200
        with _RefreshPatch(error=CrewNotFound("x")):
            assert _operator(app)[0] == 404
        with _RefreshPatch(error=RuntimeError("boom")):
            code, body, _ = _operator(app)
            assert code == 500 and json.loads(body) == {"error": "crew auth refresh failed"}
        for fragment in (
            "answers 403 to any request that carries a browser `Origin` header",
            "405 to other methods",
            "An unknown crew is 404",
            "401",
            '500 with `{"error": "crew auth refresh failed"}`',
            "Every defined outcome is HTTP 200",
        ):
            assert fragment in section, fragment

    def test_documented_outcomes_are_exactly_the_implemented_ones(self):
        assert set(_table_first_column(self.SECTION)) == set(auth_refresh.OUTCOMES)
        assert len(_table_first_column(self.SECTION)) == len(auth_refresh.OUTCOMES)

    def test_documented_response_example_has_the_implemented_shape(self):
        example = json.loads(re.search(r"```json\n(.*?)```", self.SECTION, re.S).group(1))
        with patch.object(auth_refresh._login, "_cred_store") as store:
            store.get.return_value = None
            real = auth_refresh._refresh_locked("my-crew", {"acp_backend": "kiro"})
        assert set(example) == set(real)
        assert example["status"] in auth_refresh.OUTCOMES
        assert example["crew_id"] == "my-crew" and example["backend"] == "kiro" and example["profile"] == "default"
        source = (_REPO / "transport" / "auth_refresh.py").read_text(encoding="utf-8")
        assert example["message"] in source  # the exact text the operation returns for "refreshed"

    def test_documented_method_lists_match_the_implementation(self):
        flow = re.search(r"Login-flow methods \(([^)]*)\)", self.SECTION).group(1)
        static = re.search(r"Static methods \(([^)]*)\)", self.SECTION).group(1)
        names = lambda text: set(re.findall(r"`([a-z-]+)`", text))
        assert names(flow) == {method for _backend, method in auth_refresh._FLOW_METHODS}
        assert names(static) == {method for _backend, method in launcher._STATIC_CREDENTIAL_VARIABLES}

    def test_documented_credential_missing_command_matches_the_operation_message(self):
        assert "`ghostship auth login <backend>`" in self.SECTION and "--profile <name>" in self.SECTION
        assert auth_refresh._login_command("kiro", "default") == "ghostship auth login kiro"
        assert auth_refresh._login_command("kiro", "work") == "ghostship auth login kiro --profile work"

    def test_recovery_steps_are_in_order_and_preserve_the_workspace(self):
        steps = self.SECTION[self.SECTION.index("**Recovering from `recreate_required`.**"):]
        positions = [steps.index(word) for word in ("`evac`", "`nuke`", "`launch`", "`supply`")]
        assert positions == sorted(positions)
        assert "Only after `evac` succeeds" in steps
        assert "deletes its workspace and home volumes" in steps
        # What the operation tells the operator is the same workflow and names this document.
        for message in (auth_refresh._recreate_message(True), auth_refresh._recreate_message(False)):
            assert "docs/auth.md" in message
            for word in ("evac", "nuke", "launch", "supply"):
                assert word in message

    def test_the_refresh_never_claims_to_change_the_container_or_start_stop_a_crew(self):
        assert "never starts, stops or recreates a crew" in self.SECTION
        assert "can only compare them" in self.SECTION

    def test_documented_reachability_note_matches_the_generated_portal_config(self):
        from bin.lib.caddy_install import CaddyConfig, generate_caddy_config
        assert "has no route for `/crews/*/auth/refresh`" in self.SECTION
        for key in (API_KEY, ""):
            routes = generate_caddy_config(CaddyConfig(ga_api_key=key))["apps"]["http"]["servers"]["ga-main"]["routes"]
            paths = [p for route in routes for matcher in route["match"] for p in matcher.get("path", [])]
            assert not any(fnmatch.fnmatchcase("/crews/alpha/auth/refresh", p) for p in paths)
            assert any(fnmatch.fnmatchcase("/crews/alpha/dashboard", p) for p in paths)  # the sibling it is compared to


class TestAuthDocsLifetimeEstimates:

    SECTION = _section(_AUTH_MD, "Session lifetime (estimates)")

    def test_ticket_estimates_are_present_and_attached_to_the_right_methods(self):
        rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| (.+?) \| (about \d+ days) \|$", self.SECTION, re.M)}
        assert rows == {"Codex `chatgpt`": "about 10 days", "Kiro `identity-center`": "about 90 days"}

    def test_numbers_appear_only_in_the_estimates_section(self):
        outside = _AUTH_MD.replace(self.SECTION, "")
        for number in ("10 days", "90 days", "~10", "~90"):
            assert number not in outside, number

    def test_values_are_described_as_estimates_not_guarantees(self):
        text = self.SECTION.lower()
        assert "estimates" in text
        assert "not guarantees" in text
        assert "not an expiry date" in text
        assert "depend on the provider" in text
        for overclaim in ("guaranteed", "always expires", "will expire", "expires after", "policy"):
            assert overclaim not in text, overclaim

    def test_every_listed_method_exists(self):
        from transport.credentials import SUPPORTED_METHODS
        assert "chatgpt" in SUPPORTED_METHODS["codex"]
        assert "identity-center" in SUPPORTED_METHODS["kiro"]

    def test_estimates_say_what_to_do_when_a_session_ends(self):
        assert "ghostship auth logout <backend>" in self.SECTION and "ghostship auth login <backend>" in self.SECTION


class TestAuthDocsLinks:

    def test_links_into_this_and_other_docs_resolve(self):
        section = _section(_AUTH_MD, "Refresh a crew's auth")
        local = set(re.findall(r"\]\(#([\w-]+)\)", _AUTH_MD))
        assert {"refresh-a-crews-auth", "credential-lifecycle"} <= local
        assert local <= _anchors(_AUTH_MD), local - _anchors(_AUTH_MD)
        assert "architecture.md#repository-transfer" in section
        assert "repository-transfer" in _anchors(_ARCH_MD)

    def test_the_lifecycle_paragraph_points_at_the_new_section(self):
        lifecycle = _section(_AUTH_MD, "Credential lifecycle")
        assert "[Refresh a crew's auth](#refresh-a-crews-auth)" in lifecycle


# ── docs/radar.md (task 3.2) ─────────────────────────────────────────────────

_RADAR_SECTION = _section(_RADAR_MD, "Refresh a crew's auth")
_UI = _REPO / "radar" / "web" / "src"


def _rows(section: str, first_header: str) -> list[list[str]]:
    """Body rows of the markdown table whose header starts with ``first_header``, split into cells."""
    lines = section.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"| {first_header}"))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows


def _unquote(cell: str) -> str:
    return cell.strip().strip("`")


def _radar_server():
    from tests.unit.test_radar_server import _import_radar_server
    return _import_radar_server()


def _ui(relative: str) -> str:
    """Source of one file of the Radar React app (radar/web/src)."""
    return (_UI / relative).read_text(encoding="utf-8")


def _outcome_table() -> dict[str, tuple[str, str]]:
    """Status -> (label, tone), as the React source declares them in REFRESH_OUTCOMES."""
    block = re.search(
        r"export const REFRESH_OUTCOMES[^=]*=\s*\{(.*?)\n\};", _ui("auth/refresh.ts"), re.S,
    ).group(1)
    return {
        status: (label, tone)
        for status, tone, label in re.findall(r'(\w+): \{\s*tone: "(\w+)",\s*label: "([^"]+)"', block)
    }


def _request_body_of(source: str, function: str) -> str:
    """The text of one exported async function in a TypeScript module."""
    start = source.index(f"export async function {function}(")
    end = source.index("\n}\n", start)
    return source[start:end]


class TestRadarDocsMatchTheSpa:
    """The Radar page's wording and wiring, read from radar/web/src.

    The behaviour of the same actions is asserted by Vitest
    (radar/web/test/app/refresh-auth.test.tsx); these checks keep the documented
    words and the request shape in step with the sources.
    """

    def test_documented_result_labels_and_statuses_are_the_ones_the_spa_draws(self):
        rows = _rows(_RADAR_SECTION, "Result shown")
        documented = {_unquote(status): _unquote(label) for label, status, _meaning in rows}
        assert set(documented) == set(auth_refresh.OUTCOMES)
        table = _outcome_table()
        assert set(table) == set(auth_refresh.OUTCOMES)
        for status, label in documented.items():
            assert table[status][0] == label, (status, label)

    def test_every_documented_outcome_row_carries_the_guidance_the_operation_gives(self):
        meaning = {_unquote(status): text for _label, status, text in _rows(_RADAR_SECTION, "Result shown")}
        assert "ghostship auth login <backend>" in meaning["credential_missing"]
        assert "workspace preserved" in meaning["recreate_required"]
        assert "check the transport log" in meaning["refresh_failed"].lower()

    def test_documented_failure_messages_are_what_the_spa_shows(self):
        # Key each row by the first code span in its first cell (the cell may add a link name).
        rows = {re.match(r"`([^`]+)`", r[0]).group(1): r for r in _rows(_RADAR_SECTION, "Shown")}
        notices = _ui("components/detail/CredentialsSection.tsx")
        assert "<strong>Session expired.</strong>" in notices
        assert '<a href="/dashboard/login">Sign in again</a>' in notices
        assert "**Sign in again** link" in rows["Session expired."][0]
        assert "<strong>Refresh did not complete.</strong>" in notices
        assert "Refresh did not complete." in rows
        assert "<strong>Refresh result unknown.</strong>" in notices
        assert "Refresh result unknown." in rows

    def test_documented_http_failures_are_the_ones_that_map_to_did_not_complete(self):
        cause = _rows(_RADAR_SECTION, "Shown")[1][1]
        refresh = _ui("auth/refresh.ts")
        assert "status === 403" in refresh
        assert "status === 502 || status === 503 || status === 504" in refresh
        assert "Network error. Check your connection, then retry." in refresh
        for fragment in ("502, 503 or 504", "Radar itself answers 502", "(403)", "network failed"):
            assert fragment in cause, fragment

    def test_documented_button_behaviour(self):
        text = _RADAR_SECTION
        card = _ui("components/detail/CredentialsSection.tsx")
        assert "Refresh auth" in card and '"Refreshing…"' in card
        assert "disabled={auth.busy}" in card and "aria-busy={auth.busy || undefined}" in card
        assert '<h2 className="detail-section">Credentials</h2>' in card and "**Credentials**" in text
        assert "the button is disabled and reads `Refreshing…`" in text
        assert "a second click does nothing" in text
        # The section is shown for every crew, so it is rendered without a status check.
        assert "<CredentialsSection crewId={crew.crew_id} auth={auth} />" in _ui("components/CrewDetail.tsx")
        assert "running and stopped crews" in text

    def test_documented_persistence_matches_the_row_state_handling(self):
        hook = _ui("auth/useAuthRefresh.ts")
        assert "if (!open) setNotice(null);" in hook
        assert "useAuthRefresh(crewId, open)" in _ui("components/CrewRow.tsx")
        assert "FLEET_POLL_MS = 5_000" in _ui("fleet/useFleet.ts")
        assert "stays visible across the five-second fleet refresh" in _RADAR_SECTION
        assert "cleared when the row is collapsed and reopened" in _RADAR_SECTION
        assert "Each crew is refreshed independently" in _RADAR_SECTION

    def test_documented_request_carries_no_body_and_no_credential(self):
        call = _request_body_of(_ui("auth/refresh.ts"), "requestAuthRefresh")
        assert 'method: "POST"' in call
        assert 'credentials: "include"' in call
        assert 'redirect: "manual"' in call
        assert "body:" not in call and "headers:" not in call
        assert "with no body" in _RADAR_SECTION and "it sends no credential" in _RADAR_SECTION


class TestRadarDocsMatchTheServer:

    HEADERS = {"host": "radar.example:64057", "origin": "https://radar.example:64057"}

    @staticmethod
    def _call(server, headers, *, method="POST", crew_id="alpha", status=200, content=b'{"status": "refreshed"}', error=None):
        import asyncio
        from tests.unit.test_radar_server import _call as call_app, _make_scope

        client_library = server.httpx
        seen = []

        def handle(request):
            seen.append(request)
            if error is not None:
                raise error(request)
            return client_library.Response(status, content=content, request=request)

        transport = client_library.MockTransport(handle)
        real = client_library.AsyncClient

        def client(*args, **kwargs):
            kwargs["transport"] = transport
            return real(*args, **kwargs)

        scope = _make_scope(method, f"/api/crews/{crew_id}/auth/refresh")
        scope["headers"] = [(k.encode(), v.encode()) for k, v in headers.items()]
        loop = asyncio.new_event_loop()
        try:
            with patch.object(server.httpx, "AsyncClient", side_effect=client):
                messages, body = loop.run_until_complete(call_app(server.app, scope))
        finally:
            loop.close()
        status_code = next(m["status"] for m in messages if m["type"] == "http.response.start")
        return status_code, body, seen

    def _table(self) -> dict:
        rows = _rows(_RADAR_SECTION, "Radar answers")
        return {_unquote(r[0].split(" ", 1)[0]): r for r in rows} | {r[0]: r for r in rows}

    def test_documented_answers_are_what_radar_returns(self):
        server = _radar_server()
        text = _RADAR_SECTION

        status, body, seen = self._call(server, {"host": self.HEADERS["host"]})
        assert status == 403 and json.loads(body) == {"error": "cross-origin request rejected"} and seen == []
        assert '`403` `{"error": "cross-origin request rejected"}`' in text

        status, body, seen = self._call(server, self.HEADERS, crew_id="NOT-valid")
        assert status == 404 and json.loads(body) == {"error": "crew not found"} and seen == []
        assert '`404` `{"error": "crew not found"}`' in text

        status, _body, seen = self._call(server, self.HEADERS, method="GET")
        assert status == 405 and seen == []
        assert "| `405` |" in text

        status, body, _seen = self._call(
            server, self.HEADERS, error=lambda r: server.httpx.ConnectError("refused", request=r),
        )
        assert status == 502 and json.loads(body) == {"error": "transport unreachable"}
        assert '`502` `{"error": "transport unreachable"}`' in text

        status, body, _seen = self._call(server, self.HEADERS, status=404, content=b"{}")
        assert status == 502 and json.loads(body) == {"error": "transport error", "status_code": 404}
        assert '`502` `{"error": "transport error", "status_code": <n>}`' in text

        payload = json.dumps(_outcome("recreate_required")).encode()
        status, body, _seen = self._call(server, self.HEADERS, content=payload)
        assert status == 200 and body == payload
        assert "| `200` and the transport's body |" in text

    def test_documented_timeout_is_the_implemented_one(self):
        server = _radar_server()
        assert server._AUTH_REFRESH_TIMEOUT_SECS == 60.0
        assert "within 60 seconds" in _RADAR_SECTION

    def test_browser_timeout_is_longer_than_the_server_bound_and_documented(self):
        server = _radar_server()
        refresh = _ui("auth/refresh.ts")
        browser_ms = int(re.search(r"REFRESH_TIMEOUT_MS = ([\d_]+);", refresh).group(1).replace("_", ""))
        slow_ms = int(re.search(r"SLOW_NOTE_MS = ([\d_]+);", refresh).group(1).replace("_", ""))
        assert browser_ms / 1000 == 75 and slow_ms / 1000 == 10
        assert browser_ms / 1000 > server._AUTH_REFRESH_TIMEOUT_SECS
        assert "After 10 seconds a `Still working…` note appears" in _RADAR_SECTION
        assert "within 75 seconds" in _RADAR_SECTION
        assert "`Refresh did not complete: no answer after 75 seconds.`" in _RADAR_SECTION
        assert "not a fixed result" in _RADAR_SECTION

    def test_documented_same_origin_rule_matches_the_check(self):
        server = _radar_server()
        text = _RADAR_SECTION
        for claim in (
            "exactly one `Origin` header whose host and port equal the `Host` header",
            "`SameSite=Lax`",
            "A request without an `Origin`, such as plain `curl`, is refused",
            "pass the `Host` header through unchanged",
        ):
            assert claim in text, claim
        # host and port must both match
        assert self._call(server, {"host": "a.example:1", "origin": "https://a.example:1"})[0] == 200
        assert self._call(server, {"host": "a.example:1", "origin": "https://a.example:2"})[0] == 403
        assert self._call(server, {"host": "a.example:1", "origin": "https://b.example:1"})[0] == 403
        # plain curl sends no Origin
        assert self._call(server, {"host": "a.example:1"})[0] == 403

    def test_documented_cookie_attribute_is_the_real_one(self):
        dashboard = (_REPO / "transport" / "dashboard.py").read_text(encoding="utf-8")
        assert "gs_session={token}; HttpOnly; SameSite=Lax" in dashboard

    def test_documented_forwarding_sends_only_the_transport_token(self):
        server = _radar_server()
        headers = self.HEADERS | {"cookie": "gs_session=x", "authorization": "Bearer y"}
        with patch.object(server, "_TRANSPORT_SECRET", "doc-test-secret"):
            _status, _body, seen = self._call(server, headers)
        (request,) = seen
        assert request.url.path == "/internal/crews/alpha/auth/refresh" and request.method == "POST"
        assert request.headers["x-transport-token"] == "doc-test-secret"
        sent = {name.lower() for name in request.headers.keys()}
        assert not {"cookie", "authorization", "origin"} & sent
        text = _RADAR_SECTION
        assert "with `X-Transport-Token`" in text and "passes on none of the browser's cookies or headers" in text

    def test_documented_endpoint_is_for_the_radar_page_and_points_scripts_to_the_operator_route(self):
        assert "This endpoint exists for the Radar page." in _RADAR_SECTION
        assert "auth.md#refresh-a-crews-auth" in _RADAR_SECTION


class TestRadarDocsGating:

    def _routes(self, key: str) -> list[dict]:
        from bin.lib.caddy_install import CaddyConfig, generate_caddy_config
        return generate_caddy_config(CaddyConfig(ga_api_key=key))["apps"]["http"]["servers"]["ga-main"]["routes"]

    def test_with_a_key_the_post_sits_behind_the_session_gate(self):
        from tests.unit.test_caddy_installer import REFRESH_PATH, _serve
        doc = {"apps": {"http": {"servers": {"ga-main": {"routes": self._routes("k")}}}}}
        _id, reached, _response = _serve(doc, "POST", REFRESH_PATH, auth_status=401)
        assert not any(step.startswith("ga-radar") for step in reached)
        assert _serve(doc, "POST", REFRESH_PATH, auth_status=401)[2] == {
            "status": 302, "location": "/dashboard/login?next=" + REFRESH_PATH,
        }
        text = _RADAR_SECTION
        assert "redirected to `/dashboard/login` and never reaches Radar" in text

    def test_without_a_key_nothing_gates_it_as_documented(self):
        from tests.unit.test_caddy_installer import REFRESH_PATH, _serve
        doc = {"apps": {"http": {"servers": {"ga-main": {"routes": self._routes("")}}}}}
        _id, reached, response = _serve(doc, "POST", REFRESH_PATH, auth_status=401)
        assert reached == ["ga-radar:8080" + REFRESH_PATH] and response == {"proxied": True}
        text = _RADAR_SECTION
        assert "**Tailscale-gated installs have no portal session.**" in text
        assert "anyone who can reach Radar on the tailnet" in text
        assert "same-origin rule still stops other web pages" in text

    def test_documented_limits_of_the_action_are_real(self):
        # "It can only re-apply the credential already stored for that crew's own backend and profile."
        import inspect
        assert list(inspect.signature(auth_refresh.refresh_crew_auth).parameters) == ["crew_id"]
        assert "It cannot supply or choose a credential" in _RADAR_SECTION

    def test_the_auth_section_still_says_the_key_less_install_skips_the_session_check(self):
        auth = _section(_RADAR_MD, "Auth")
        assert "When `GA_API_KEY` is unset, session check is skipped" in auth
        assert "[Refresh auth](#refresh-a-crews-auth)" in auth and "same-origin `Origin` header" in auth
        # "with or without a key": the check is in Radar's handler, which takes no session or key input,
        # so it runs on every request. Only the missing Origin differs between callers.
        assert "with or without a key" in auth
        import ast
        import inspect
        import textwrap
        server = _radar_server()
        assert "_is_same_origin(request)" in inspect.getsource(server.api_crew_auth_refresh)
        check = ast.parse(textwrap.dedent(inspect.getsource(server._is_same_origin))).body[0]
        code = ast.Module(body=check.body[1:], type_ignores=[])  # drop the docstring, keep the logic
        read = {n.value for n in ast.walk(code) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        assert read == {"origin", "host", "http", "https"}, read  # no cookie, key or session input
        assert [a.arg for a in check.args.args] == ["request"]


class TestRadarDocsLinks:

    def test_anchors_resolve(self):
        assert "refresh-a-crews-auth" in _anchors(_RADAR_MD)
        assert "auth" in _anchors(_RADAR_MD)
        assert {"refresh-a-crews-auth", "credential-lifecycle"} <= _anchors(_AUTH_MD)
        local = set(re.findall(r"\]\(#([\w-]+)\)", _RADAR_MD))
        assert local <= _anchors(_RADAR_MD), local - _anchors(_RADAR_MD)

    def test_cross_document_links_resolve(self):
        for target in re.findall(r"\]\((auth\.md#[\w-]+)\)", _RADAR_MD):
            assert target.split("#", 1)[1] in _anchors(_AUTH_MD), target
        for target in re.findall(r"\]\((radar\.md#[\w-]+)\)", _AUTH_MD):
            assert target.split("#", 1)[1] in _anchors(_RADAR_MD), target

    def test_radar_doc_names_no_credential_or_secret_values(self):
        for forbidden in ("Bearer ey", "sk-", "gs_session=", "ga-api-key"):
            assert forbidden not in _RADAR_SECTION, forbidden
