"""Unit tests for the TRN-97 ``GA_LIGHTHOUSE_ENABLED`` config flag.

Verifies the ``Config`` dataclass default and ``Config.from_env()`` parsing
(via the existing ``_env_bool_default_off`` helper).
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from transport.config import Config


class LighthouseConfigTests(unittest.TestCase):
    def test_default_is_false(self) -> None:
        self.assertFalse(Config().ga_lighthouse_enabled)

    def test_from_env_unset_defaults_false(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "GA_LIGHTHOUSE_ENABLED"}
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(Config.from_env().ga_lighthouse_enabled)

    def test_from_env_true(self) -> None:
        with patch.dict(os.environ, {"GA_LIGHTHOUSE_ENABLED": "true"}, clear=False):
            self.assertTrue(Config.from_env().ga_lighthouse_enabled)

    def test_from_env_accepts_truthy_synonyms(self) -> None:
        for val in ("1", "yes", "on", "TRUE", "On"):
            with self.subTest(val=val):
                with patch.dict(os.environ, {"GA_LIGHTHOUSE_ENABLED": val}, clear=False):
                    self.assertTrue(Config.from_env().ga_lighthouse_enabled)

    def test_from_env_zero_is_false(self) -> None:
        with patch.dict(os.environ, {"GA_LIGHTHOUSE_ENABLED": "0"}, clear=False):
            self.assertFalse(Config.from_env().ga_lighthouse_enabled)

    def test_from_env_false_and_empty_are_false(self) -> None:
        for val in ("false", "", "no"):
            with self.subTest(val=val):
                with patch.dict(os.environ, {"GA_LIGHTHOUSE_ENABLED": val}, clear=False):
                    self.assertFalse(Config.from_env().ga_lighthouse_enabled)


if __name__ == "__main__":
    unittest.main()
