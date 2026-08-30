"""Unit tests for ``transport.registry`` — crew registry + schedule persistence.

TRN-85 Phase 1 stub. Migration target for classes whose function-under-test is
defined in ``registry.py`` (``_load_registry``, ``_save_registry``,
``_get_crew``, ``_touch_crew``, ``_get_crew_schedules``,
``_upsert_crew_schedule``, ``_remove_crew_schedule``, ``_advance_next_fire_at``).
Patch via ``transport.registry`` — the call-site principle: these run in
registry.py's namespace even though ``server`` re-exports them.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch  # noqa: F401

from tests.unit.helpers import registry, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
