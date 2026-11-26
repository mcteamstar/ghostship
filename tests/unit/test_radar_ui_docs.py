"""Docs-versus-UI checks for the Radar page (TRN-371, task 6.9).

docs/radar.md names what the page shows and how it behaves. These checks confirm that the
documented wording is in the docs, and that the React source and stylesheet draw the same
wording and use the same breakpoint and theme rules. The behaviour itself is covered by the
Vitest suite in radar/web/test.
"""
from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).parents[2]
_RADAR_MD = (_REPO / "docs" / "radar.md").read_text(encoding="utf-8")
_UI = _REPO / "radar" / "web" / "src"
_CSS = (_UI / "styles" / "radar.css").read_text(encoding="utf-8")
_REQUEST_TS = (_UI / "api" / "request.ts").read_text(encoding="utf-8")


def _ui_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted([*_UI.rglob("*.tsx"), *_UI.rglob("*.ts")])
    )


# Wording the docs promise. Each one must appear in docs/radar.md.
DOCUMENTED_WORDING = (
    "Running · N",
    "Finished · N",
    "unknown agent",
    "No crews match filter.",
    "No active tasks.",
    "No messages.",
    "Loading tasks…",
    "Loading mailbox subjects…",
    "Active tasks unavailable.",
    "Mailbox subjects unavailable.",
    "Session expired, sign in again",
    "Free memory",
    "Capacity",
)

# The same wording as the React source draws it. The running and finished counts are
# built at render time, so their fixed prefixes are what the source holds.
UI_WORDING = (
    "Running · ",
    "Finished · ",
    "unknown agent",
    "No crews match filter.",
    "No active tasks.",
    "No messages.",
    "Loading tasks…",
    "Loading mailbox subjects…",
    "Active tasks unavailable.",
    "Mailbox subjects unavailable.",
    "Session expired, sign in again",
    "Free memory",
    "Capacity",
)


def test_documented_wording_is_in_the_docs() -> None:
    missing = [phrase for phrase in DOCUMENTED_WORDING if phrase not in _RADAR_MD]
    assert missing == []


def test_documented_wording_is_what_the_ui_draws() -> None:
    source = _ui_source()
    missing = [phrase for phrase in UI_WORDING if phrase not in source]
    assert missing == []


def test_documented_breakpoint_is_the_stylesheet_breakpoint() -> None:
    assert "below 640 px" in _RADAR_MD.lower()
    assert "@media (max-width: 639px)" in _CSS


def test_documented_themes_follow_the_system_preference() -> None:
    assert "system colour preference" in _RADAR_MD
    assert "@media (prefers-color-scheme: dark)" in _CSS


def test_documented_filter_is_always_shown() -> None:
    assert "The filter above the table is always shown." in _RADAR_MD
    app = (_UI / "App.tsx").read_text(encoding="utf-8")
    assert "<FleetFilter value={filter} onChange={setFilter} />" in app
    assert "FILTER_THRESHOLD" not in app


def test_session_expiry_is_documented_as_the_request_wrapper_classifies_it() -> None:
    # An HTML page answered with HTTP 200 is a session expiry. Any other non-JSON answer is a
    # failed request for its section. The docs and request.ts must draw that same line.
    assert "answered with HTTP 200 and an HTML page" in _RADAR_MD
    assert "is a failed request for its section and never shows that note" in _RADAR_MD
    assert 'contentType.includes("text/html")' in _REQUEST_TS
    assert 'new RequestError("http-error", "Non-JSON response"' in _REQUEST_TS


def test_scheduled_jobs_section_is_gone_from_the_docs_and_the_ui() -> None:
    assert "scheduled jobs" not in _RADAR_MD.lower()
    assert "crons" not in _ui_source().lower()
