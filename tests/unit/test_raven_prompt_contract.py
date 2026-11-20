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


def test_captain_dispatch_policy_covers_pacing_memory_deferral_and_resumption() -> None:
    import transport.captain as captain

    prompt = captain._CAPTAIN_CHECKIN_TASK
    assert "one new task start per check-in is the default" in prompt
    assert "explicitly authorizes several independent tasks" in prompt
    assert "a separate reconciled intent and task ID for each" in prompt

    policy = captain._RAVEN_DISPATCH_PACING
    assert "Start them sequentially" in policy
    assert "memory_pressure:" in policy
    assert "start no further tasks in this check-in" in policy
    assert "reconcile prior intents and task IDs before retrying" in policy
    assert "confirm each accepted task is visible before starting the next" in policy


def test_every_builtin_order_receives_the_shared_dispatch_policy() -> None:
    import transport.captain as captain

    root = Path(__file__).resolve().parents[2]
    order_dir = root / "academy" / "orders"
    expected = {
        "free-will.md",
        "independent-review.md",
        "repo-hygiene-sweep.md",
        "spec-driven-development.md",
    }
    paths = {path.name: path for path in order_dir.glob("*.md")}
    assert set(paths) == expected

    for name in sorted(expected):
        raw = paths[name].read_text(encoding="utf-8")
        assert "{{RAVEN_DISPATCH_PACING}}" in raw, name
        resolved = captain._substitute_placeholders(raw)
        assert "## Paced dispatch and reconciliation" in resolved, name
        assert "memory_pressure:" in resolved, name
        assert "confirm each accepted task is visible before starting the next" in resolved, name


def test_multi_task_orders_key_intents_by_change_or_review_track() -> None:
    import transport.captain as captain

    root = Path(__file__).resolve().parents[2] / "academy" / "orders"
    indy = captain._substitute_placeholders((root / "independent-review.md").read_text())
    assert "seven independent reviewer work items" in indy
    assert "scope and review track" in indy
    assert "an active Banshee task for one track does not block another track" in indy

    sweepy = captain._substitute_placeholders((root / "repo-hygiene-sweep.md").read_text())
    assert "four independent read-only work items" in sweepy
    assert "exact task prefix" in sweepy

    sdd = captain._substitute_placeholders((root / "spec-driven-development.md").read_text())
    assert "same `<change>/<persona>` key" in sdd
    assert "start those change/persona work items sequentially" in sdd
    assert "stop all further starts across the change list" in sdd
