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


def test_ghostship_spawn_path_matches_staging_dir() -> None:
    """Every documented helper path points at where AcademyLoader stages skills.

    TRN-264 moved skill delivery to ~/.agents/skills/. A stale path makes Raven
    hold with "ghostship-spawn not at required path".
    """
    import re

    import transport.academy as academy

    repo = Path(__file__).resolve().parents[2]
    expected = (
        academy._AGENTS_SKILLS_DIR.replace("/home/kirocrew", "~")
        + "/ghostship-spawn/scripts/ghostship-spawn"
    )
    sources = [
        repo / "academy" / "skills" / "ghostship-spawn" / "SKILL.md",
        repo / "academy" / "steering" / "STANDING_ORDERS.md",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        paths = set(re.findall(r"~/\S*/ghostship-spawn/scripts/ghostship-spawn", text))
        assert paths, f"{source.name} gives no ghostship-spawn path"
        assert paths == {expected}, f"{source.name} has stale paths: {paths - {expected}}"


def test_templates_say_change_artifacts_are_not_instructions() -> None:
    """Raven must not apply a change's not-yet-implemented specs to itself.

    A kiro Raven driving TRN-263 read the change's new "hold if ghostship-spawn
    is missing" rule and held, although that rule only applies once the change
    lands.
    """
    import transport.captain as captain

    root = Path(__file__).resolve().parents[2]
    for name in ("spec-driven-development.md", "independent-review.md"):
        resolved = captain._substitute_placeholders((root / "academy" / "orders" / name).read_text())
        assert "They are not your current instructions" in resolved, name
