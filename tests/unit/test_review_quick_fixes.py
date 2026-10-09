"""Small fixes from the 0.6.0 independent review.

- Dashboard ``next``: a backslash path (``/\\evil.com``) is an open redirect,
  because browsers treat ``\\`` as ``/``.
- Float settings: ``nan`` and ``inf`` are rejected (a NaN threshold never trips).
- Backend list: the shell parser rejects a line break, as the Python one does.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.unit._stubs import install_import_stubs
install_import_stubs()

from transport.config import Config, ConfigError, parse_agent_backends  # noqa: E402
import transport.dashboard as dashboard  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "scripts" / "lib" / "agent_backends.sh"


class TestNextUrl(unittest.TestCase):
    def test_backslash_redirects_are_rejected(self):
        for url in ("/\\evil.com", "/\\\\evil.com", "/a\\b"):
            with self.subTest(url=url):
                self.assertEqual(dashboard._validate_next_url(url), "/")

    def test_control_characters_are_rejected(self):
        self.assertEqual(dashboard._validate_next_url("/a\nb"), "/")

    def test_normal_paths_are_kept(self):
        for url in ("/", "/crews/x/ui", "/dashboard?tab=1"):
            with self.subTest(url=url):
                self.assertEqual(dashboard._validate_next_url(url), url)

    def test_existing_protections_still_hold(self):
        for url in ("//evil.com", "https://evil.com", "javascript:alert(1)", ""):
            with self.subTest(url=url):
                self.assertEqual(dashboard._validate_next_url(url), "/")


class TestFiniteFloats(unittest.TestCase):
    def test_nan_and_inf_are_rejected(self):
        for value in ("nan", "NaN", "inf", "-inf"):
            with self.subTest(value=value):
                with patch.dict("os.environ", {"GA_MIN_FREE_MEM_GB": value}, clear=True):
                    with self.assertRaises(ConfigError):
                        Config.from_env()

    def test_normal_float_accepted(self):
        with patch.dict("os.environ", {"GA_MIN_FREE_MEM_GB": "1.5"}, clear=True):
            self.assertEqual(Config.from_env().ga_min_free_mem_gb, 1.5)


class TestBackendListLineBreak(unittest.TestCase):
    def test_both_parsers_reject_a_line_break(self):
        raw = "claude,codex\nbogus"
        with self.assertRaises(ConfigError):
            parse_agent_backends(raw)
        result = subprocess.run(
            ["bash", "-c", f'source "{LIB}"; agent_backends_normalise "$1"', "bash", raw],
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("single line", result.stderr)


if __name__ == "__main__":
    unittest.main()
