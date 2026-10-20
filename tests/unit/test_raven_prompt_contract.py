"""Guard every Raven prompt source against unsafe gateway-call drift."""

from __future__ import annotations

import json
from pathlib import Path


def test_all_raven_prompt_sources_use_ghostship_spawn() -> None:
    root = Path(__file__).resolve().parents[2]
    raven = json.loads((root / "academy" / "agents" / "raven.json").read_text())

    import transport.captain as captain

    sources = {
        "raven.json": raven["prompt"],
        "orientation": captain._RAVEN_GATEWAY_ORIENTATION,
        "check-in": captain._CAPTAIN_CHECKIN_TASK,
    }
    for path in sorted((root / "academy" / "orders").glob("*.md")):
        raw = path.read_text()
        sources[f"{path.name} (raw)"] = raw
        sources[f"{path.name} (resolved)"] = captain._substitute_placeholders(raw)

    forbidden = (
        ".local_secret",
        "X-Internal-Secret",
        "X-Session-Key",
        ".dashboard_cookie",
        "curl",
        "-d @",
        "--data @",
        "--data-binary @",
    )
    for name, text in sources.items():
        assert "ghostship-spawn" in text, name
        for token in forbidden:
            assert token not in text, f"{token!r} leaked into {name}"
