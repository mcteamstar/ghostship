"""Raven's persona prompt must agree with Captain's gateway orientation."""
import json
from pathlib import Path

from transport import captain

_ROOT = Path(__file__).resolve().parents[2]
_HELPER = "~/.agents/skills/ghostship-spawn/scripts/ghostship-spawn"


def _raven_prompt() -> str:
    return json.loads((_ROOT / "academy" / "agents" / "raven.json").read_text())["prompt"]


def test_raven_persona_embeds_captain_gateway_orientation_verbatim():
    assert captain._RAVEN_GATEWAY_ORIENTATION in _raven_prompt()


def test_raven_is_never_told_to_avoid_its_own_task_list_helper():
    prompt = _raven_prompt()
    for sentence in prompt.split(". "):
        if "Do not use" in sentence:
            assert _HELPER not in sentence, sentence
    assert "Do not use `kirocrew spawn list`" in prompt
