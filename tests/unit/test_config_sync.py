"""Unit tests for Config/conf.example field sync -- every Config field must have a commented entry in ghostship.conf.example."""

import dataclasses
import re
import unittest
from pathlib import Path

try:
    from transport.config import Config
except ModuleNotFoundError:  # pragma: no cover - container flat layout
    from config import Config  # type: ignore

REPO_ROOT = Path(__file__).resolve().parents[2]
CONF_EXAMPLE = REPO_ROOT / "config" / "ghostship.conf.example"


class TestConfigConfExampleSync(unittest.TestCase):
    def test_every_config_field_present_in_conf_example(self):
        text = CONF_EXAMPLE.read_text()
        # An entry looks like a commented assignment: "# GA_MAX_CREWS=..." —
        # match the env var name at the start of a commented line, allowing
        # for leading whitespace, so we don't get fooled by prose mentions.
        present = set(
            re.findall(r"(?m)^\s*#\s*([A-Z][A-Z0-9_]*)\s*=", text)
        )

        missing = []
        for f in dataclasses.fields(Config):
            env_name = f.name.upper()
            if env_name not in present:
                missing.append(env_name)

        self.assertEqual(
            missing,
            [],
            "Config fields missing a commented entry in "
            f"{CONF_EXAMPLE.name}: {missing}. Add each as a commented-out line "
            "(e.g. '# GA_FOO=default').",
        )


if __name__ == "__main__":
    unittest.main()
