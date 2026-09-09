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


class HostMemoryHelpersTests(unittest.TestCase):
    """Direct unit tests for _get_host_memory_gb and _get_host_memory_gb_cached (nit 5.4)."""

    def test_get_host_memory_gb_returns_available_in_gb(self) -> None:
        """_get_host_memory_gb converts memAvailable bytes to GB."""
        fake = FakePodmanClient([int(8 * 1024**3)])
        result = podman._get_host_memory_gb(fake)
        self.assertAlmostEqual(result, 8.0, places=1)
        self.assertEqual(fake.system_info_calls, 1)

    def test_get_host_memory_gb_fractional_value(self) -> None:
        """_get_host_memory_gb handles fractional GB correctly."""
        fake = FakePodmanClient([int(2.5 * 1024**3)])
        result = podman._get_host_memory_gb(fake)
        self.assertAlmostEqual(result, 2.5, places=1)

    def test_get_host_memory_gb_cached_returns_fresh_value_on_empty_cache(self) -> None:
        """_get_host_memory_gb_cached fetches fresh value when cache is empty."""
        podman._host_memory_cache = None
        fake = FakePodmanClient([int(4 * 1024**3)])
        with patch("time.monotonic", return_value=200.0):
            result = podman._get_host_memory_gb_cached(fake)
        self.assertAlmostEqual(result, 4.0, places=1)
        self.assertEqual(fake.system_info_calls, 1)

    def test_get_host_memory_gb_cached_returns_none_on_failure(self) -> None:
        """_get_host_memory_gb_cached returns None when system_info() raises."""

        class FailingPodman:
            def system_info(self) -> dict:
                raise RuntimeError("no socket")

        podman._host_memory_cache = None
        with patch("time.monotonic", return_value=300.0):
            result = podman._get_host_memory_gb_cached(FailingPodman())
        self.assertIsNone(result)


class PodmanSecretTests(unittest.TestCase):
    """TRN-136: secret_create / secret_remove and the container_create secrets param.

    A real ``PodmanClient`` is constructed, then its ``_c`` (httpx client) and
    ``_req`` are replaced with fakes that record the HTTP calls so the tests
    assert on the request shape without a live Podman socket.
    """

    def _client(self):
        # __init__ opens a UDS httpx client against a socket path; pass a dummy
        # path and immediately swap the client for a recorder.
        client = podman.PodmanClient.__new__(podman.PodmanClient)
        client._sock_path = "/nonexistent.sock"
        return client

    def test_secret_create_posts_raw_bytes_with_name(self) -> None:
        client = self._client()
        recorded = {}

        class FakeResp:
            status_code = 201
            def raise_for_status(self):  # pragma: no cover - not reached on 201
                pass

        class FakeHTTP:
            def post(self, path, params=None, content=None, headers=None):
                recorded["path"] = path
                recorded["params"] = params
                recorded["content"] = content
                recorded["headers"] = headers
                return FakeResp()

        client._c = FakeHTTP()
        client.secret_create("admiral-pubkey-demo", b"\x01" * 32)

        self.assertEqual(recorded["path"], "/libpod/secrets/create")
        self.assertEqual(recorded["params"], {"name": "admiral-pubkey-demo"})
        self.assertEqual(recorded["content"], b"\x01" * 32)

    def test_secret_create_conflict_removes_then_recreates(self) -> None:
        client = self._client()
        calls = []

        class Resp409:
            status_code = 409
            def raise_for_status(self):  # pragma: no cover
                pass

        class Resp201:
            status_code = 201
            def raise_for_status(self):
                pass

        class FakeHTTP:
            def __init__(self):
                self._post_count = 0
            def post(self, path, params=None, content=None, headers=None):
                self._post_count += 1
                calls.append(("post", params["name"]))
                # First create → 409 conflict; second create (after remove) → 201.
                return Resp409() if self._post_count == 1 else Resp201()
            def delete(self, path):
                calls.append(("delete", path))
                class D:
                    def raise_for_status(self_inner):
                        pass
                return D()

        client._c = FakeHTTP()
        client.secret_create("admiral-pubkey-demo", b"\x02" * 32)

        self.assertEqual(calls[0], ("post", "admiral-pubkey-demo"))
        self.assertEqual(calls[1], ("delete", "/libpod/secrets/admiral-pubkey-demo"))
        self.assertEqual(calls[2], ("post", "admiral-pubkey-demo"))

    def test_secret_remove_deletes_by_name_and_swallows_errors(self) -> None:
        client = self._client()
        recorded = {}

        class FakeHTTP:
            def delete(self, path):
                recorded["path"] = path
                class D:
                    def raise_for_status(self_inner):
                        pass
                return D()

        client._c = FakeHTTP()
        client.secret_remove("admiral-pubkey-demo")
        self.assertEqual(recorded["path"], "/libpod/secrets/admiral-pubkey-demo")

        # A raising delete must be swallowed (best-effort).
        class RaisingHTTP:
            def delete(self, path):
                raise RuntimeError("boom")

        client._c = RaisingHTTP()
        client.secret_remove("admiral-pubkey-demo")  # must not raise

    def test_container_create_includes_secrets_when_provided(self) -> None:
        client = self._client()
        captured = {}

        def fake_req(method, path, json=None):
            captured["method"] = method
            captured["path"] = path
            captured["json"] = json
            return {}

        client._req = fake_req
        secrets_arg = [{
            "source": "admiral-pubkey-demo",
            "target": "/home/kirocrew/.kiro/crew/.admiral_public_key",
            "uid": 0, "gid": 0, "mode": 0o444,
        }]
        client.container_create(
            name="gs-demo", image="img", env={}, network="ga-starboard",
            workspace_volume="vol", home_volume="home", secrets=secrets_arg,
        )
        self.assertEqual(captured["json"]["secrets"], secrets_arg)
        # Hardening flags are preserved.
        self.assertTrue(captured["json"]["no_new_privileges"])
        self.assertIn("CAP_SYS_ADMIN", captured["json"]["cap_drop"])

    def test_container_create_omits_secrets_key_when_none(self) -> None:
        client = self._client()
        captured = {}

        def fake_req(method, path, json=None):
            captured["json"] = json
            return {}

        client._req = fake_req
        client.container_create(
            name="gs-demo", image="img", env={}, network="ga-starboard",
            workspace_volume="vol", home_volume="home",
        )
        self.assertNotIn("secrets", captured["json"])


if __name__ == "__main__":
    unittest.main()
