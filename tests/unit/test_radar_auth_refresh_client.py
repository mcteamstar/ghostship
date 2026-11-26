"""Client tests for the Radar "Refresh auth" action (TRN-367).

Runs the real radar/static/render.js and state.js under Node with a stubbed
``fetch`` and a stub detail row, then checks what the action sends and what it
draws:

- the request: ``POST /api/crews/{id}/auth/refresh`` with session credentials,
  ``redirect: "manual"``, no body and no headers (so nothing credential-bearing);
- every outcome is shown with its own label and the transport's guidance, and
  the guidance is HTML-escaped; fields other than ``status`` and ``message`` are
  never drawn;
- a second click while a request is in flight does nothing, and the button is
  drawn disabled, including after a fleet-poll re-render;
- an expired portal session (login redirect or login page) is reported as
  "session expired, sign in again", never as an outcome;
- network and HTTP failures are reported as "did not complete".
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).parents[2]
_RADAR_STATIC = _REPO / "radar" / "static"
_RENDER_JS = _RADAR_STATIC / "render.js"

_DRIVER = """
const url = process.env.RENDER_JS_URL;
const scenario = process.env.SCENARIO;
const arg = process.env.ARG ? JSON.parse(process.env.ARG) : {};

// A stub row: redrawOpenDetail() looks the open row up by id and rewrites its
// .detail-inner, so the stub records what the live DOM would show.
const inner = { innerHTML: "" };
const detailRow = { querySelector: (sel) => (sel === ".detail-inner" ? inner : null) };
globalThis.document = {
  getElementById: (id) => (id === "detail-alpha" ? detailRow : {}),
  querySelector: () => null,
  querySelectorAll: () => [],
};
const mod = await import(url);
const state = await import(new URL("./state.js", url).href);

const crew = Object.assign({ crew_id: "alpha", status: "running" }, arg.crew || {});
const calls = [];
const held = [];

function makeResponse(spec) {
  if (spec.kind === "opaqueredirect") {
    return {
      type: "opaqueredirect", status: 0, ok: false, redirected: false,
      headers: { get: () => null },
      json: () => Promise.reject(new Error("opaque redirect has no body")),
    };
  }
  const status = spec.status === undefined ? 200 : spec.status;
  const contentType = spec.contentType === undefined ? "application/json" : spec.contentType;
  return {
    type: "basic", status, ok: status >= 200 && status < 300, redirected: !!spec.redirected,
    headers: { get: (name) => (name.toLowerCase() === "content-type" ? contentType : null) },
    json: () => (spec.badJson ? Promise.reject(new SyntaxError("bad json")) : Promise.resolve(spec.body)),
  };
}

globalThis.fetch = (target, options) => {
  calls.push({ target, options });
  const spec = arg.response || { body: { status: "refreshed", message: "ok" } };
  if (spec.kind === "throw") throw new TypeError("fetch is not available");
  if (spec.kind === "reject") return Promise.reject(new TypeError("Failed to fetch"));
  if (spec.hold) return new Promise((resolve) => held.push(() => resolve(makeResponse(spec))));
  return Promise.resolve(makeResponse(spec));
};

function openRow() {
  state.openDetails.add("alpha");
  state.setLastData({ crews: [crew] });
  inner.innerHTML = mod.renderOpenDetail(crew);
}

const out = { crew };
switch (scenario) {
  case "render": {
    out.html = mod.renderDetail(crew);
    break;
  }
  case "single": {
    openRow();
    out.initial = inner.innerHTML;
    const pending = mod.refreshCrewAuth("alpha");
    out.during = inner.innerHTML;
    out.callsDuringCall = calls.length;
    if (held.length) held.shift()();
    out.returned = await pending;
    out.after = inner.innerHTML;
    out.rerender = mod.renderOpenDetail(crew);
    out.busy = state.authRefreshing.size;
    break;
  }
  case "closed": {
    out.returned = await mod.refreshCrewAuth("alpha");
    out.cache = state.detailCache.has("alpha");
    out.busy = state.authRefreshing.size;
    break;
  }
  case "duplicate": {
    openRow();
    const first = mod.refreshCrewAuth("alpha");
    const second = mod.refreshCrewAuth("alpha");
    out.secondReturned = await second;
    out.callsWhileBusy = calls.length;
    out.busyHtml = mod.renderDetail(crew);
    held.shift()();
    await first;
    out.idleHtml = mod.renderDetail(crew);
    const third = mod.refreshCrewAuth("alpha");
    out.callsAfterThird = calls.length;
    held.shift()();
    await third;
    out.busy = state.authRefreshing.size;
    break;
  }
  case "other_crew_not_blocked": {
    openRow();
    const first = mod.refreshCrewAuth("alpha");
    const other = mod.refreshCrewAuth("bravo");
    out.targets = calls.map((c) => c.target);
    held.shift()();
    held.shift()();
    await Promise.all([first, other]);
    out.busy = state.authRefreshing.size;
    break;
  }
  case "collapse_while_busy": {
    openRow();
    const pending = mod.refreshCrewAuth("alpha");
    const before = inner.innerHTML;
    state.openDetails.delete("alpha");
    state.clearDetailCache("alpha");
    held.shift()();
    await pending;
    out.rowUntouched = inner.innerHTML === before;
    out.cache = state.detailCache.has("alpha");
    out.busy = state.authRefreshing.size;
    break;
  }
  case "reopen_while_busy": {
    openRow();
    const pending = mod.refreshCrewAuth("alpha");
    state.clearDetailCache("alpha"); // collapse then expand: the cache is cleared, the row is open
    out.busyHtml = mod.renderOpenDetail(crew);
    held.shift()();
    await pending;
    out.after = inner.innerHTML;
    break;
  }
  case "redraw_cycle": {
    openRow();
    await mod.refreshCrewAuth("alpha");
    const callsBefore = calls.length;
    out.pollRerender = mod.renderOpenDetail(crew);
    out.refetched = calls.length !== callsBefore;
    state.clearDetailCache("alpha");
    out.afterCollapse = mod.renderOpenDetail(crew);
    break;
  }
  case "wire": {
    const listeners = [];
    const root = { addEventListener: (type, fn, capture) => listeners.push({ type, capture }) , _fns: [] };
    const fns = [];
    root.addEventListener = (type, fn, capture) => { listeners.push({ type, capture }); fns.push(fn); };
    mod.wireAuthRefresh(root);
    out.listeners = listeners;
    let stopped = 0;
    const button = { dataset: { authRefresh: arg.crewId || "alpha" } };
    fns[0]({ target: { closest: (sel) => (sel === "[data-auth-refresh]" ? button : null) },
             stopPropagation: () => { stopped += 1; } });
    out.callsAfterButtonClick = calls.map((c) => c.target);
    out.stoppedAfterButtonClick = stopped;
    fns[0]({ target: { closest: () => null }, stopPropagation: () => { stopped += 1; } });
    fns[0]({ target: {}, stopPropagation: () => { stopped += 1; } });
    fns[0]({ target: null, stopPropagation: () => { stopped += 1; } });
    out.callsAfterOtherClicks = calls.length;
    out.stoppedAfterOtherClicks = stopped;
    break;
  }
  default:
    throw new Error("unknown scenario " + scenario);
}
out.calls = calls;
console.log(JSON.stringify(out));
"""


def _run_scenario(tmp_path: Path, scenario: str, **arg) -> dict:
    driver = tmp_path / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    # Resolve node from the caller's PATH (fnm, nvm, Homebrew) but run it with a
    # minimal environment.
    node = shutil.which("node")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "RENDER_JS_URL": _RENDER_JS.as_uri(),
        "SCENARIO": scenario,
        "ARG": json.dumps(arg),
    }
    proc = subprocess.run(
        [node, str(driver)], env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

OUTCOMES = {
    "refreshed": "Refreshed.",
    "pending_on_wake": "Pending until wake.",
    "current": "Already current.",
    "recreate_required": "Recreate required.",
    "credential_missing": "No credential stored.",
    "refresh_failed": "Refresh failed.",
}
TONES = {
    "refreshed": "auth-ok",
    "pending_on_wake": "auth-info",
    "current": "auth-ok",
    "recreate_required": "auth-warn",
    "credential_missing": "auth-warn",
    "refresh_failed": "auth-error",
}


def _json(status: str, **extra) -> dict:
    return {"body": {"status": status, "message": f"guidance for {status}", **extra}}


@needs_node
class TestRefreshRequest:

    def test_posts_to_the_refresh_endpoint_with_session_credentials_and_manual_redirect(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response=_json("refreshed"))
        assert len(result["calls"]) == 1
        call = result["calls"][0]
        assert call["target"] == "/api/crews/alpha/auth/refresh"
        assert call["options"] == {"method": "POST", "credentials": "include", "redirect": "manual"}

    def test_request_carries_no_body_headers_or_credential(self, tmp_path):
        options = _run_scenario(tmp_path, "single", response=_json("refreshed"))["calls"][0]["options"]
        for forbidden in ("body", "headers", "mode", "referrer"):
            assert forbidden not in options

    def test_crew_id_is_url_encoded_in_the_request_path(self, tmp_path):
        result = _run_scenario(tmp_path, "wire", crewId="we ird/id")
        assert result["callsAfterButtonClick"] == ["/api/crews/we%20ird%2Fid/auth/refresh"]


@needs_node
class TestOutcomesAreRendered:

    @pytest.mark.parametrize("status", sorted(OUTCOMES))
    def test_each_outcome_has_its_own_label_tone_and_guidance(self, tmp_path, status):
        result = _run_scenario(tmp_path, "single", response=_json(status))
        for html in (result["after"], result["rerender"]):
            assert f"<strong>{OUTCOMES[status]}</strong>" in html
            assert f"guidance for {status}" in html
            assert TONES[status] in html
            for other, label in OUTCOMES.items():
                if other != status:
                    assert label not in html
        assert result["returned"] == result["after"].split('<div class="auth-refresh">')[1].split(
            "</button>", 1
        )[1].rsplit("</div>", 1)[0]

    @pytest.mark.parametrize("status", sorted(OUTCOMES))
    def test_default_guidance_is_shown_when_the_response_has_none(self, tmp_path, status):
        result = _run_scenario(tmp_path, "single", response={"body": {"status": status}})
        assert f"<strong>{OUTCOMES[status]}</strong>" in result["after"]
        assert "undefined" not in result["after"]
        # recreate_required points at the documented workflow even without a message
        if status == "recreate_required":
            assert "docs/auth.md" in result["after"]

    def test_non_string_or_empty_message_falls_back_to_default_guidance(self, tmp_path):
        for message in (None, "", 7, {"a": 1}, ["x"]):
            result = _run_scenario(
                tmp_path, "single", response={"body": {"status": "refreshed", "message": message}},
            )
            assert "The stored credential was injected into the running crew." in result["after"]
            assert "[object Object]" not in result["after"]

    def test_guidance_is_html_escaped_and_not_executed(self, tmp_path):
        hostile = "<img src=x onerror=alert(1)> & <script>alert(2)</script> \"quoted\""
        html = _run_scenario(tmp_path, "single", response=_json("refresh_failed") | {
            "body": {"status": "refresh_failed", "message": hostile},
        })["after"]
        assert "<img" not in html and "<script" not in html
        assert "&lt;img src=x onerror=alert(1)&gt;" in html
        assert "&amp;" in html and "&quot;quoted&quot;" in html

    def test_only_status_and_message_are_drawn(self, tmp_path):
        response = {"body": {
            "status": "refreshed", "message": "ok", "crew_id": "alpha", "backend": "kiro",
            "profile": "default", "token": "SENTINEL-TOKEN", "payload": "SENTINEL-PAYLOAD",
            "credential": "SENTINEL-CREDENTIAL", "authorization": "SENTINEL-BEARER",
        }}
        html = _run_scenario(tmp_path, "single", response=response)["after"]
        assert "SENTINEL" not in html

    @pytest.mark.parametrize("status", ["constructor", "__proto__", "toString", "hasOwnProperty", "<b>x</b>", "", "REFRESHED", 7, None])
    def test_unrecognised_status_is_never_drawn_as_an_outcome(self, tmp_path, status):
        html = _run_scenario(
            tmp_path, "single", response={"body": {"status": status, "message": "should not be shown"}},
        )["after"]
        assert "<strong>Refresh result unknown.</strong>" in html
        assert "should not be shown" not in html
        assert "<b>x</b>" not in html
        for label in OUTCOMES.values():
            assert label not in html

    def test_non_object_bodies_are_unknown_results(self, tmp_path):
        for body in (None, "refreshed", 3, [], ["refreshed"]):
            html = _run_scenario(tmp_path, "single", response={"body": body})["after"]
            assert "Refresh result unknown." in html

    def test_unparseable_json_is_an_unknown_result(self, tmp_path):
        html = _run_scenario(tmp_path, "single", response={"badJson": True})["after"]
        assert "Refresh result unknown." in html


@needs_node
class TestSessionExpiry:

    EXPIRED = "<strong>Session expired.</strong>"

    def _assert_expired(self, html: str) -> None:
        assert self.EXPIRED in html
        assert 'href="/dashboard/login"' in html
        assert "Sign in again" in html
        for label in OUTCOMES.values():
            assert label not in html
        assert "did not complete" not in html

    def test_login_redirect_is_session_expired(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"kind": "opaqueredirect"})
        self._assert_expired(result["after"])
        assert result["calls"][0]["options"]["redirect"] == "manual"

    def test_followed_redirect_is_session_expired(self, tmp_path):
        result = _run_scenario(
            tmp_path, "single", response={"redirected": True, "contentType": "text/html; charset=utf-8", "body": "<html>"},
        )
        self._assert_expired(result["after"])

    def test_login_page_served_with_200_is_session_expired(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"contentType": "text/html", "body": {"status": "refreshed"}})
        self._assert_expired(result["after"])

    def test_a_json_outcome_that_happens_to_follow_a_redirect_is_not_trusted(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"redirected": True, "body": {"status": "refreshed", "message": "ok"}})
        self._assert_expired(result["after"])

    def test_expiry_is_cached_so_a_poll_rerender_keeps_it(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"kind": "opaqueredirect"})
        self._assert_expired(result["rerender"])

    def test_button_is_usable_again_after_expiry(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"kind": "opaqueredirect"})
        assert "disabled" not in result["after"]
        assert result["busy"] == 0


@needs_node
class TestFailures:

    DID_NOT_COMPLETE = "<strong>Refresh did not complete.</strong>"

    def test_http_errors_are_did_not_complete_with_specific_guidance(self, tmp_path):
        cases = {
            502: "could not get a result from ga-transport",
            503: "could not get a result from ga-transport",
            504: "could not get a result from ga-transport",
            403: "same-origin check",
            404: "HTTP 404",
            500: "HTTP 500",
        }
        for status, text in cases.items():
            result = _run_scenario(
                tmp_path, "single", response={"status": status, "body": {"error": "transport unreachable", "detail": "SENTINEL"}},
            )
            assert self.DID_NOT_COMPLETE in result["after"], status
            assert text in result["after"], status
            assert "SENTINEL" not in result["after"], status
            assert "Session expired" not in result["after"], status
            for label in OUTCOMES.values():
                assert label not in result["after"], status

    def test_an_error_page_is_not_mistaken_for_session_expiry(self, tmp_path):
        result = _run_scenario(
            tmp_path, "single", response={"status": 502, "contentType": "text/html", "body": "<html>Bad Gateway</html>"},
        )
        assert self.DID_NOT_COMPLETE in result["after"]
        assert "Session expired" not in result["after"]

    def test_network_error_is_did_not_complete(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"kind": "reject"})
        assert self.DID_NOT_COMPLETE in result["after"]
        assert "Network error" in result["after"]
        assert result["busy"] == 0
        assert "disabled" not in result["after"]

    def test_fetch_that_throws_synchronously_still_releases_the_button(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"kind": "throw"})
        assert self.DID_NOT_COMPLETE in result["after"]
        assert result["busy"] == 0
        assert "disabled" not in result["after"]

    def test_a_failed_refresh_can_be_retried(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response={"status": 502, "body": {}})
        assert 'data-auth-refresh="alpha"' in result["after"]
        assert "disabled" not in result["after"]


@needs_node
class TestDuplicateSubmissions:

    def test_second_click_while_in_flight_sends_nothing(self, tmp_path):
        result = _run_scenario(tmp_path, "duplicate", response=_json("refreshed") | {"hold": True})
        assert result["secondReturned"] is None
        assert result["callsWhileBusy"] == 1

    def test_button_is_disabled_and_labelled_while_in_flight(self, tmp_path):
        result = _run_scenario(tmp_path, "duplicate", response=_json("refreshed") | {"hold": True})
        busy = result["busyHtml"]
        button = re.search(r"<button[^>]*data-auth-refresh=\"alpha\"[^>]*>([^<]*)</button>", busy)
        assert button, busy
        assert " disabled" in button.group(0) and 'aria-busy="true"' in button.group(0)
        assert button.group(1) == "Refreshing…"

    def test_button_is_enabled_again_when_the_request_finishes_and_a_new_one_is_allowed(self, tmp_path):
        result = _run_scenario(tmp_path, "duplicate", response=_json("refreshed") | {"hold": True})
        idle = re.search(r"<button[^>]*data-auth-refresh=\"alpha\"[^>]*>([^<]*)</button>", result["idleHtml"])
        assert idle and " disabled" not in idle.group(0)
        assert idle.group(1) == "Refresh auth"
        assert result["callsAfterThird"] == 2
        assert result["busy"] == 0

    def test_a_refresh_of_one_crew_does_not_block_another(self, tmp_path):
        result = _run_scenario(tmp_path, "other_crew_not_blocked", response=_json("refreshed") | {"hold": True})
        assert result["targets"] == ["/api/crews/alpha/auth/refresh", "/api/crews/bravo/auth/refresh"]
        assert result["busy"] == 0

    def test_in_flight_state_is_drawn_into_the_live_row_at_the_start(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response=_json("refreshed") | {"hold": True})
        assert " disabled" in result["during"] and "Refreshing…" in result["during"]
        assert OUTCOMES["refreshed"] not in result["during"]
        assert result["callsDuringCall"] == 1

    def test_result_replaces_the_previous_outcome_when_a_new_request_starts(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response=_json("refreshed") | {"hold": True})
        assert "auth-refresh-result" not in result["during"]


@needs_node
class TestSurvivesFleetPollRerender:
    """The fleet table is rebuilt on every poll; the action's state must survive it."""

    def test_busy_state_and_outcome_survive_a_poll_rerender(self, tmp_path):
        result = _run_scenario(tmp_path, "single", response=_json("pending_on_wake"))
        assert "<strong>Pending until wake.</strong>" in result["rerender"]
        assert result["rerender"] == result["after"]

    def test_poll_rerender_does_not_refetch_or_resubmit(self, tmp_path):
        result = _run_scenario(tmp_path, "redraw_cycle", response=_json("refreshed"))
        assert result["refetched"] is False
        assert len(result["calls"]) == 1
        assert "<strong>Refreshed.</strong>" in result["pollRerender"]

    def test_outcome_is_dropped_when_the_row_is_collapsed_and_reopened(self, tmp_path):
        result = _run_scenario(tmp_path, "redraw_cycle", response=_json("refreshed"))
        assert "auth-refresh-result" not in result["afterCollapse"]
        assert 'data-auth-refresh="alpha"' in result["afterCollapse"]

    def test_row_reopened_during_a_request_still_shows_the_button_disabled(self, tmp_path):
        result = _run_scenario(tmp_path, "reopen_while_busy", response=_json("refreshed") | {"hold": True})
        assert " disabled" in result["busyHtml"]
        assert "<strong>Refreshed.</strong>" in result["after"]

    def test_row_collapsed_during_a_request_is_not_redrawn_and_caches_nothing(self, tmp_path):
        result = _run_scenario(tmp_path, "collapse_while_busy", response=_json("refreshed") | {"hold": True})
        assert result["rowUntouched"] is True
        assert result["cache"] is False
        assert result["busy"] == 0

    def test_a_refresh_for_a_row_that_is_not_open_still_completes_cleanly(self, tmp_path):
        result = _run_scenario(tmp_path, "closed", response=_json("refreshed"))
        assert "<strong>Refreshed.</strong>" in result["returned"]
        assert result["cache"] is False
        assert result["busy"] == 0


@needs_node
class TestPanelMarkup:

    def test_every_crew_gets_a_credentials_section_with_the_button(self, tmp_path):
        for status in ("running", "stopped"):
            html = _run_scenario(tmp_path, "render", crew={"status": status})["html"]
            assert '<div class="detail-section">Credentials</div>' in html
            assert 'data-auth-refresh="alpha"' in html
            assert ">Refresh auth</button>" in html
            assert " disabled" not in html

    def test_button_is_a_non_submitting_button(self, tmp_path):
        html = _run_scenario(tmp_path, "render")["html"]
        assert '<button type="button" class="auth-refresh-btn"' in html

    def test_crew_id_is_escaped_in_the_attribute(self, tmp_path):
        html = _run_scenario(tmp_path, "render", crew={"crew_id": 'a"><img src=x onerror=1>'})["html"]
        assert "<img" not in html
        assert "data-auth-refresh=\"a&quot;&gt;&lt;img src=x onerror=1&gt;\"" in html

    def test_no_result_is_shown_before_any_refresh(self, tmp_path):
        assert "auth-refresh-result" not in _run_scenario(tmp_path, "render")["html"]

    def test_markup_holds_no_credential_or_transport_secret_names(self, tmp_path):
        html = _run_scenario(tmp_path, "single", response=_json("refreshed"))["after"]
        for forbidden in ("Authorization", "Bearer", "X-Transport-Token", "gs_session", "api-key", "password"):
            assert forbidden not in html


@needs_node
class TestClickWiring:

    def test_one_delegated_click_listener_is_registered(self, tmp_path):
        result = _run_scenario(tmp_path, "wire", response=_json("refreshed"))
        assert result["listeners"] == [{"type": "click"}]

    def test_clicking_a_refresh_button_starts_one_refresh_and_stops_propagation(self, tmp_path):
        result = _run_scenario(tmp_path, "wire", response=_json("refreshed"))
        assert result["callsAfterButtonClick"] == ["/api/crews/alpha/auth/refresh"]
        assert result["stoppedAfterButtonClick"] == 1

    def test_other_clicks_are_ignored_without_error(self, tmp_path):
        result = _run_scenario(tmp_path, "wire", response=_json("refreshed"))
        assert result["callsAfterOtherClicks"] == 1
        assert result["stoppedAfterOtherClicks"] == 1


class TestWiringAndPolling:
    """Source-level guards: the action is wired in once and polling never triggers it."""

    def test_main_registers_the_action_on_the_fleet_body(self):
        source = (_RADAR_STATIC / "main.js").read_text(encoding="utf-8")
        assert 'import { renderTable, wireAuthRefresh } from "./render.js";' in source
        handler = source.index('document.addEventListener("DOMContentLoaded"')
        assert handler < source.index("wireAuthRefresh(bodyEl);")
        assert source.count("wireAuthRefresh(") == 1

    def test_refresh_request_is_made_only_by_the_refresh_function(self):
        source = _RENDER_JS.read_text(encoding="utf-8")
        url = '"/auth/refresh"'  # the request URL literal; comments do not quote it
        assert source.count(url) == 1
        refresh = source.index("export function refreshCrewAuth")
        assert refresh < source.index(url) < source.index("export function wireAuthRefresh")
        assert 'method: "POST"' in source and 'redirect: "manual"' in source

    def test_fleet_polling_and_row_expansion_never_start_a_refresh(self):
        data_js = (_RADAR_STATIC / "data.js").read_text(encoding="utf-8")
        assert "auth/refresh" not in data_js and "refreshCrewAuth" not in data_js
        render = _RENDER_JS.read_text(encoding="utf-8")
        # Besides its definition, refreshCrewAuth is called from exactly one place:
        # the delegated click handler, which only a user's click on the button reaches.
        sites = [m.start() for m in re.finditer(r"(?<!function )refreshCrewAuth\(", render)]
        assert len(sites) == 1
        wire = render.index("export function wireAuthRefresh")
        assert wire < sites[0]
        assert render.index("refreshCrewAuth(btn.dataset.authRefresh)") == sites[0]
        # Row expansion (the table click handler in renderTable) does not start one.
        expand = render[render.index('tr.addEventListener("click"'):render.index("/* Update \"Last Task\" header")]
        assert "refreshCrewAuth" not in expand

    def test_stylesheet_defines_every_class_the_action_uses(self):
        css = (_RADAR_STATIC / "style.css").read_text(encoding="utf-8")
        for selector in (
            ".auth-refresh", ".auth-refresh-btn", ".auth-refresh-btn:disabled", ".auth-refresh-result",
            ".auth-ok", ".auth-info", ".auth-warn", ".auth-error",
        ):
            assert selector in css, selector
