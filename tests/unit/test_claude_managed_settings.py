"""Unit tests for the claude toolchain's managed settings (TRN-262).

Covers:
- claude-managed-settings.json disables commit and PR attribution, and has no
  deprecated includeCoAuthoredBy key
- the attribution check rejects any non-empty commit or pr string
- claude.sh installs the file to the managed-settings path
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLCHAINS = REPO_ROOT / "crews" / "spec-ops" / "toolchains"
SETTINGS_PATH = TOOLCHAINS / "claude-managed-settings.json"
CLAUDE_SH_PATH = TOOLCHAINS / "claude.sh"
MANAGED_PATH = "/etc/claude-code/managed-settings.json"


def _assert_attribution_disabled(settings: dict[str, Any]) -> None:
    attribution = settings.get("attribution")
    assert isinstance(attribution, dict), "attribution must be an object"
    assert attribution.get("commit") == "", "attribution.commit must be empty"
    assert attribution.get("pr") == "", "attribution.pr must be empty"
    assert "includeCoAuthoredBy" not in settings, "deprecated key must be absent"


def test_managed_settings_disable_attribution() -> None:
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    _assert_attribution_disabled(settings)


@pytest.mark.parametrize(
    "settings",
    [
        {"attribution": {"commit": "Co-Authored-By: Claude", "pr": ""}},
        {"attribution": {"commit": "", "pr": "Generated with Claude Code"}},
        {"attribution": False},
        {"attribution": {"commit": "", "pr": ""}, "includeCoAuthoredBy": True},
    ],
)
def test_attribution_check_rejects_enabled_settings(settings: dict[str, Any]) -> None:
    with pytest.raises(AssertionError):
        _assert_attribution_disabled(settings)


def test_claude_sh_installs_managed_settings() -> None:
    text = CLAUDE_SH_PATH.read_text(encoding="utf-8")
    assert "claude-managed-settings.json" in text
    assert MANAGED_PATH in text
