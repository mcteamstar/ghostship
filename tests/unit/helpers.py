"""Shared test helpers for the modularised transport unit suite (TRN-85).

The ~8500-line ``test_transport.py`` is being split into one test file per
transport module (``test_registry.py``, ``test_podman.py``, ``test_files.py``,
``test_captain.py``, ``test_academy.py``, ``test_lifecycle.py``,
``test_server.py``). This module holds the pieces shared *across* those files:

* the ``server`` module handle, imported via the dependency-free bootstrap in
  ``test_file_transfer._install_import_stubs`` (so the suite runs inside a crew
  container with no ``httpx``/``mcp``/``starlette`` installed), and the
  per-module aliases (``registry``, ``podman``, ``files_mod``, ``captain_mod``,
  ``academy``, ``lifecycle``);
* mock factories used by test classes that land in more than one file.

Phase-2 migration moves genuinely cross-file mock factories here; single-cluster
helpers move with the class cluster that uses them.
"""

from __future__ import annotations

from typing import Any  # noqa: F401  (used by helpers added during migration)

# Reuse the dependency-free import bootstrap: importing ``server`` from
# test_file_transfer installs the stdlib stubs (httpx/mcp/starlette/uvicorn)
# on first import if the real packages are absent, then hands back the real
# ``transport.server`` module.
from tests.unit.test_file_transfer import server  # noqa: F401  (re-exported)

import transport.registry as registry  # noqa: F401  (re-exported)
import transport.podman as podman  # noqa: F401  (re-exported)
import transport.files as files_mod  # noqa: F401  (re-exported)
import transport.captain as captain_mod  # noqa: F401  (re-exported)
import transport.academy as academy  # noqa: F401  (re-exported)
import transport.lifecycle as lifecycle  # noqa: F401  (re-exported)
