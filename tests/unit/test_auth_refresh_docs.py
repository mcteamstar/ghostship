"""Docs-versus-implementation checks for the crew auth refresh feature (TRN-367).

The operator documentation names routes, outcomes, response fields, status codes
and session-lifetime estimates. These tests read docs/auth.md (and, for the
Radar half, docs/radar.md) and check each claim against the code that
implements it, so the docs cannot drift from the routes without a test failing.
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
    start = next(i for i, line in enumerate(lines) if re.match(r"#+ " + re.escape(heading) + r"\s*$", line))
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
