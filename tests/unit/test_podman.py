"""Unit tests for ``transport.podman`` — container runtime + host-memory gate.

TRN-85 Phase 1 stub. Migration target for classes whose function-under-test is
defined in ``podman.py`` (``PodmanClient``, ``_get_podman``, ``_http``,
``_async_http``, ``_get_host_memory_gb``, ``_get_host_memory_gb_cached``,
``_wait_for_memory``). Patch via ``transport.podman``. Where a class drives an
MCP tool (``crews``) to observe the cache, patch ``server.<tool>`` for the call
site and ``podman._host_memory_cache`` for the observed global.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch  # noqa: F401

from tests.unit.helpers import podman, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
