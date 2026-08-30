"""Unit tests for ``transport.captain`` — Captain standing orders + mail helpers.

TRN-85: migration target for classes whose function-under-test is defined in
``captain.py`` (``_append_captain_mail``, ``_format_captain_mail``,
``_captain_jobs``, ``_captain_standing_view``, ``_load_order_template``,
``_resolve_order_template``, ``_mail_count``, ``_read_all_mail_*``). Patch via
``transport.captain``. Captain calls lifecycle's ``_crew_api_with_recovery``;
patch ``transport.lifecycle._crew_api_with_recovery`` for that dependency.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import captain_mod, lifecycle, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
