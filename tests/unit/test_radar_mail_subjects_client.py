"""Client tests for the Radar mailbox-subject section (TRN-370).

Runs the real radar/static/render.js under Node with a stubbed fetch and a
minimal container, then checks the rendered HTML for each state: subjects,
empty mailboxes, escaped subject text, and the single unavailable state.

Also checks that the mailbox request is wired only to row expansion, never to
the fleet polling path.
"""
from __future__ import annotations

import json
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
// render.js reads the fleet table at module load. The loader under test never
// touches it, so an empty element stub is enough to import the module.
globalThis.document = {
  getElementById: () => ({}),
  querySelector: () => null,
  querySelectorAll: () => [],
};
const mod = await import(url);
const state = await import(new URL("./state.js", url).href);
if (process.env.OPEN === "1") state.openDetails.add("alpha");

const calls = [];
globalThis.fetch = (target, opts) => {
  calls.push({ target, credentials: opts && opts.credentials });
  switch (scenario) {
    case "subjects":
      return Promise.resolve({ ok: true, json: () => Promise.resolve({
        mailboxes: {
          ghost: ["<img src=x onerror=alert(1)> hi"],
          spectre: [],
          banshee: ["plain"],
          wraith: [], reaper: [], raven: [], captain: [], admiral: [],
        },
      }) });
    case "http_503":
      return Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) });
    case "network_error":
      return Promise.reject(new Error("offline"));
    case "missing_mailboxes":
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ error: "x" }) });
    default:
      throw new Error("unknown scenario " + scenario);
  }
};

const container = {
  html: "",
  insertAdjacentHTML(position, html) {
    if (position !== "beforeend") throw new Error("unexpected position " + position);
    this.html += html;
  },
};

await mod.loadMailSubjects("alpha", container);
// What a poll re-render draws for the open row, without fetching again.
const callsBeforeRedraw = calls.length;
const redraw = mod.renderOpenDetail({ crew_id: "alpha", status: "stopped" });
console.log(JSON.stringify({
  calls, html: container.html, redraw, redrawFetched: calls.length !== callsBeforeRedraw,
}));
"""


def _run_scenario(tmp_path: Path, scenario: str, *, open_row: bool = False) -> dict:
    driver = tmp_path / "driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    # Resolve node from the caller's PATH (fnm, nvm, Homebrew) but run it with a
    # minimal environment.
    node = shutil.which("node")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "RENDER_JS_URL": _RENDER_JS.as_uri(),
        "SCENARIO": scenario,
        "OPEN": "1" if open_row else "0",
    }
    proc = subprocess.run(
        [node, str(driver)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

MAILBOX_ORDER = ["ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral"]


@needs_node
class TestMailSubjectsRendering:

    def test_requests_mailbox_subjects_with_session_credentials(self, tmp_path):
        result = _run_scenario(tmp_path, "subjects")
        assert result["calls"] == [
            {"target": "/api/crews/alpha/mail-subjects", "credentials": "include"}
        ]

    def test_all_eight_mailboxes_render_in_order(self, tmp_path):
        html = _run_scenario(tmp_path, "subjects")["html"]
        positions = [html.index(f"<strong>{name}</strong>") for name in MAILBOX_ORDER]
        assert positions == sorted(positions)

    def test_subject_text_is_escaped_and_not_executed(self, tmp_path):
        html = _run_scenario(tmp_path, "subjects")["html"]
        assert "&lt;img src=x onerror=alert(1)&gt; hi" in html
        assert "<img" not in html

    def test_empty_mailboxes_show_explicit_empty_state(self, tmp_path):
        html = _run_scenario(tmp_path, "subjects")["html"]
        assert html.count("No messages.") == 6
        assert "<li>plain</li>" in html

    def test_unavailable_state_on_http_error(self, tmp_path):
        html = _run_scenario(tmp_path, "http_503")["html"]
        assert "Mailbox subjects unavailable." in html
        assert "No messages." not in html
        assert "<strong>" not in html

    def test_unavailable_state_on_network_error(self, tmp_path):
        html = _run_scenario(tmp_path, "network_error")["html"]
        assert "Mailbox subjects unavailable." in html
        assert "No messages." not in html

    def test_unavailable_state_on_payload_without_mailboxes(self, tmp_path):
        html = _run_scenario(tmp_path, "missing_mailboxes")["html"]
        assert "Mailbox subjects unavailable." in html
        assert "No messages." not in html


@needs_node
class TestOpenRowSurvivesPollRerender:
    """A poll re-render redraws the fetched subjects for an open row without refetching."""

    def test_open_row_redraw_keeps_subjects(self, tmp_path):
        result = _run_scenario(tmp_path, "subjects", open_row=True)
        assert "Mailbox subjects" in result["redraw"]
        assert "<li>plain</li>" in result["redraw"]
        assert "&lt;img src=x onerror=alert(1)&gt; hi" in result["redraw"]
        assert "<img" not in result["redraw"]
        assert result["redrawFetched"] is False

    def test_open_row_redraw_keeps_unavailable_state(self, tmp_path):
        result = _run_scenario(tmp_path, "http_503", open_row=True)
        assert "Mailbox subjects unavailable." in result["redraw"]
        assert "No messages." not in result["redraw"]

    def test_closed_row_is_not_cached(self, tmp_path):
        result = _run_scenario(tmp_path, "subjects", open_row=False)
        assert "Mailbox subjects" not in result["redraw"]


class TestMailboxReadsStayOffFleetPolling:
    """The mailbox request must run only from the row-expansion handler."""

    def test_render_module_calls_mailbox_loader_only_in_row_click(self):
        source = _RENDER_JS.read_text(encoding="utf-8")
        call_site = source.index("if (crew) loadMailSubjects(crewId, inner);")
        click_handler = source.index('tr.addEventListener("click"')
        assert click_handler < call_site
        # The only call to the loader is that one inside the click handler.
        assert source.count("loadMailSubjects(") == 2  # the call site and its definition

    def test_fleet_polling_module_does_not_reference_mailbox_route(self):
        data_js = (_RADAR_STATIC / "data.js").read_text(encoding="utf-8")
        assert "mail-subjects" not in data_js
        assert "loadMailSubjects" not in data_js
