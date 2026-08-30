"""Unit tests for ``transport.server`` — MCP tools, routes, middleware, proxy.

TRN-85: migration target for classes testing the MCP tool surface
(``crews``, ``launch``, ``dispatch``, ``pickup``, ``steer``, ``nuke``,
``captain``, ``schedule``, ``evac``, ``supply``, ``resource_*``), the login
state machine routes (``_handle_login_post``/``_get``, ``_handle_logout_post``),
the bearer-auth middleware, and the crew proxy handlers.

Patch rule: patch ``server.<name>`` for names resolved in server's body (the
call site of a lifecycle/academy function imported by name). Patch
``lifecycle.<dep>`` / ``academy.<dep>`` for a dependency called two levels deep
inside the lifecycle/academy function (e.g. mock ``lifecycle._http`` inside a
``_crew_api_with_recovery`` path, ``lifecycle._crew_api as api`` for pickup).
Legitimate two-level patches (server call-site + lifecycle internal dep) are
NOT the dual-patch anti-pattern and are kept.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import server, lifecycle, academy  # noqa: F401


if __name__ == "__main__":
    unittest.main()
