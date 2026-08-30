"""Unit tests for ``transport.academy`` — crew-type composition + manifest resolution.

TRN-85 / TRN-86: migration target for classes whose function-under-test is
defined in ``academy.py`` (``COMPOSITION_REGISTRY``, ``_load_composition_registry``,
``_resolve_composition``, ``_resolve_manifest_path``, ``_resolve_image``,
``_load_crew_manifest``, ``_manifest_selects``, ``_substitute_env_vars``,
``_validate_academy``, ``_AGENTS_DIR``, ``_CREW_REGISTRY_PATH``).

This file ABSORBS the existing ``test_academy_validation.py`` and
``test_crew_types.py``. Patch via ``transport.academy`` exclusively — the
dual-patches on ``lifecycle``/``server`` for these names (from TRN-71) are now
wrong and collapse to single ``transport.academy`` patches. Where an MCP tool
(``launch``, ``compositions``) is driven at the call site, patch ``server.<tool>``.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import academy, lifecycle, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
