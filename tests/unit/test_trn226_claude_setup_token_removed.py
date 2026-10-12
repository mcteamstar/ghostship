"""TRN-226: the broken ``POST /login/claude/setup-token`` route is removed.

``claude setup-token`` prints a long-lived token after an interactive browser
approval; it never writes ``~/.claude/.credentials.json``, so the route could
not complete, and its blocking exec hung the event loop. Headless Claude auth
is now ``CLAUDE_CODE_OAUTH_TOKEN`` in ghostship.conf (see
test_trn226_claude_oauth_token.py). These tests keep the route from coming back.
"""

from __future__ import annotations

import unittest
from pathlib import Path

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as server  # noqa: E402

_SERVER_SRC = Path(server.__file__).read_text()


class TestSetupTokenRouteRemoved(unittest.TestCase):
    def test_route_not_registered(self) -> None:
        """No route table maps /login/claude/setup-token, so it falls through to 404."""
        self.assertNotIn('"/login/claude/setup-token"', _SERVER_SRC)

    def test_handler_removed(self) -> None:
        self.assertFalse(hasattr(server, "_handle_claude_setup_token_post"))

    def test_lifecycle_function_removed(self) -> None:
        """No code path starts a login container to run ``claude setup-token``."""
        self.assertFalse(hasattr(_lifecycle, "_initiate_claude_setup_token"))
        self.assertFalse(hasattr(server, "_initiate_claude_setup_token"))

    def test_interactive_oauth_routes_unchanged(self) -> None:
        for route in ('"/login/claude"', '"/login/claude/code"', '"/logout/claude"'):
            self.assertIn(route, _SERVER_SRC)


if __name__ == "__main__":
    unittest.main()
