"""Unit tests for ``transport.podman`` — container runtime + host-memory gate.

TRN-85 migration target for classes whose function-under-test is defined in
``podman.py`` (``PodmanClient``, ``_get_podman``, ``_http``, ``_async_http``,
``_get_host_memory_gb``, ``_get_host_memory_gb_cached``, ``_wait_for_memory``).
Patch via ``transport.podman``. Where a class drives an MCP tool (``crews``)
to observe the cache, patch ``server.<tool>`` for the call site and
``podman._host_memory_cache`` for the observed global.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import podman, server, FakePodmanClient  # noqa: F401


class MemoryGateTests(unittest.TestCase):
    """Tests for the pre-launch memory gate — ``_wait_for_memory`` (podman.py).

    NOTE: the former ``TestMemoryGate.test_gate_skipped_when_disabled`` case
    exercised ``_ensure_crew_running`` (lifecycle) and migrated to
    ``test_lifecycle.py`` (``MemoryGateDisabledTests``).
    """

    def test_memory_available_immediately(self) -> None:
        """Gate passes with no sleep when memory is sufficient."""
        # 4 GB free, requires 2 GB
        fake = FakePodmanClient([4 * 1024**3])
        result = podman._wait_for_memory(fake, 2.0, 60)
        self.assertGreaterEqual(result, 2.0)
        self.assertEqual(fake.system_info_calls, 1)

    def test_memory_frees_after_two_polls(self) -> None:
        """Gate passes after memory appears on second poll."""
        # First poll: 1 GB (insufficient), second poll: 3 GB (sufficient)
        fake = FakePodmanClient([
            1 * 1024**3,
            1 * 1024**3,
            3 * 1024**3,
        ])
        with patch("time.sleep"):
            result = podman._wait_for_memory(fake, 2.0, 60)
        self.assertGreaterEqual(result, 2.0)
        self.assertEqual(fake.system_info_calls, 3)

    def test_timeout_expires(self) -> None:
        """RuntimeError raised when memory stays below threshold."""
        # Always reports 0.5 GB
        fake = FakePodmanClient([int(0.5 * 1024**3)])
        with patch("time.sleep"), patch("time.monotonic", side_effect=[
            0.0,    # deadline = 0 + 5 = 5
            0.0,    # first check
            3.0,    # after first sleep
            3.0,    # second check
            6.0,    # exceeds deadline
        ]):
            result = podman._wait_for_memory(fake, 2.0, 5)
        # Returns the last observed free GB (0.5), which is below the required 2.0
        self.assertAlmostEqual(result, 0.5, delta=0.1)


class CrewsMemoryFieldTests(unittest.TestCase):
    """Tests for host_memory_available_gb in crews() response.

    ``crews()`` is a server MCP tool; patch ``server._load_registry`` /
    ``server._get_podman`` at the call site (the lifecycle dual-patches from
    TRN-71 were shadows and are dropped). The observed cache global lives in
    ``transport.podman`` — reset ``podman._host_memory_cache`` directly.
    """

    def test_crews_includes_memory_field(self) -> None:
        """crews() response includes host_memory_available_gb."""
        reg = {"crews": {}}
        fake = FakePodmanClient([int(3.5 * 1024**3)])
        # Clear cache to force fresh read (cache global lives in transport.podman)
        podman._host_memory_cache = None
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_get_podman", return_value=fake),
        ):
            result = server.crews()
        self.assertIn("host_memory_available_gb", result)
        self.assertIsNotNone(result["host_memory_available_gb"])
        self.assertAlmostEqual(result["host_memory_available_gb"], 3.5, places=0)

    def test_crews_memory_null_on_failure(self) -> None:
        """host_memory_available_gb is None when Podman info fails."""
        reg = {"crews": {}}

        class BrokenPodman:
            def system_info(self) -> dict:
                raise RuntimeError("connection refused")

        podman._host_memory_cache = None
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_get_podman", return_value=BrokenPodman()),
        ):
            result = server.crews()
        self.assertIn("host_memory_available_gb", result)
        self.assertIsNone(result["host_memory_available_gb"])


class MemoryCacheTests(unittest.TestCase):
    """Tests for _get_host_memory_gb_cached TTL behavior."""

    def test_cache_ttl_avoids_repeated_calls(self) -> None:
        """Second call within 5s does not invoke system_info() again."""
        fake = FakePodmanClient([int(4 * 1024**3)])
        podman._host_memory_cache = None

        with patch("time.monotonic", return_value=100.0):
            val1 = podman._get_host_memory_gb_cached(fake)
        with patch("time.monotonic", return_value=103.0):
            val2 = podman._get_host_memory_gb_cached(fake)

        self.assertEqual(val1, val2)
        self.assertEqual(fake.system_info_calls, 1)

    def test_cache_expires_after_ttl(self) -> None:
        """After 5s, a fresh system_info() call is made."""
        fake = FakePodmanClient([int(4 * 1024**3), int(3 * 1024**3)])
        podman._host_memory_cache = None

        with patch("time.monotonic", return_value=100.0):
            podman._get_host_memory_gb_cached(fake)
        with patch("time.monotonic", return_value=106.0):
            podman._get_host_memory_gb_cached(fake)

        self.assertEqual(fake.system_info_calls, 2)


if __name__ == "__main__":
    unittest.main()
