"""TRN-75: CI sync check between the Config dataclass and ghostship.conf.example.

Every runtime env var the transport reads is declared as a field on
`transport.config.Config`. Field names mirror the env var name lowercased
(e.g. GA_MAX_CREWS -> ga_max_crews), so the env var for a field is
`field.name.upper()`.

This test asserts every Config field has a corresponding commented-out entry
in `config/ghostship.conf.example`, so a new config option can never be added
to the code without also being documented in the example config file.
"""

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
