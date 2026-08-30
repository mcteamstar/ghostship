"""Unit tests for ``transport.lifecycle`` — crew setup / registration lifecycle.

TRN-85 Phase 1 stub. Migration target for classes whose function-under-test is
defined in ``lifecycle.py`` (``_ensure_crew_running``, ``_finish_crew_setup``,
``_crew_api_with_recovery``, ``_crew_api``, ``_probe_gateway``,
``_patch_crew_config``, ``_copy_agents``, ``_copy_skills``, ``_inject_policy``,
``_inject_git_identity``, ``_mint_cookie``, ``_reconcile_registry``, the login
state machine) — **not** the academy functions (those go to ``test_academy.py``).

Patch via ``transport.lifecycle`` for owning-module functions. When a name is
called from server's namespace (e.g. ``_nuke_login_container`` invoked inside
``server._handle_login_*``), patch ``server.<name>`` for the assertion and
``lifecycle.<dep>`` for a dependency internal to the lifecycle function.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch  # noqa: F401

from tests.unit.helpers import lifecycle, academy, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
