"""TRN-231: GA_REQUIRE_API_KEY defaults to error on non-loopback installs.

Covers the transport startup gate ``transport.server._enforce_require_api_key``:

  (a) exits on a non-loopback bind with no key when GA_REQUIRE_API_KEY=error
      (and when unset, since error is now the default);
  (b) does not exit on loopback with no key regardless of the setting;
  (c) does not exit with GA_REQUIRE_API_KEY=off on non-loopback with no key;
  (d) warn is still accepted (log and continue);
  (e) a present API key never triggers the gate.

Enforcement is a dedicated function called from the startup path (not at module
import), so importing ``transport.server`` never terminates the process.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import server  # noqa: F401  (shared import bootstrap)


class RequireApiKeyStartupGate(unittest.TestCase):
    def _enforce(self, api_key: str, env: dict) -> None:
        """Call the gate with a clean environment (only the given keys set)."""
        clean = {k: v for k, v in {
            "HOST": None,
            "GA_REQUIRE_API_KEY": None,
            **env,
        }.items() if v is not None}
        with patch.dict("os.environ", clean, clear=False):
            import os

            # Remove any inherited values not explicitly set for this case.
            if "HOST" not in env:
                os.environ.pop("HOST", None)
            if "GA_REQUIRE_API_KEY" not in env:
                os.environ.pop("GA_REQUIRE_API_KEY", None)
            server._enforce_require_api_key(api_key)

    def test_a_error_nonloopback_no_key_exits(self):
        with self.assertRaises(SystemExit) as cm:
            self._enforce("", {"HOST": "0.0.0.0", "GA_REQUIRE_API_KEY": "error"})
        self.assertEqual(cm.exception.code, 1)

    def test_a_default_nonloopback_no_key_exits(self):
        # GA_REQUIRE_API_KEY unset -> defaults to error -> exits.
        with self.assertRaises(SystemExit) as cm:
            self._enforce("", {"HOST": "0.0.0.0"})
        self.assertEqual(cm.exception.code, 1)

    def test_b_loopback_no_key_starts(self):
        for host in ("127.0.0.1", "::1", "localhost"):
            with self.subTest(host=host):
                # No SystemExit raised.
                self._enforce("", {"HOST": host, "GA_REQUIRE_API_KEY": "error"})

    def test_b_loopback_default_starts(self):
        self._enforce("", {"HOST": "127.0.0.1"})

    def test_c_off_nonloopback_no_key_starts(self):
        self._enforce("", {"HOST": "0.0.0.0", "GA_REQUIRE_API_KEY": "off"})

    def test_d_warn_nonloopback_no_key_starts(self):
        self._enforce("", {"HOST": "0.0.0.0", "GA_REQUIRE_API_KEY": "warn"})

    def test_e_present_key_never_exits(self):
        # A present key short-circuits before any bind-address check.
        self._enforce("secret", {"HOST": "0.0.0.0", "GA_REQUIRE_API_KEY": "error"})


if __name__ == "__main__":
    unittest.main()
