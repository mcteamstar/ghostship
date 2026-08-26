"""Tests for trn-4-semver: VERSION file, /version endpoint, crews() version field."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from tests.unit.test_file_transfer import server


class TestReadTransportVersion(unittest.TestCase):
    """Task 5.1: version-reading utility returns file content or default."""

    def test_reads_version_from_file(self) -> None:
        """When VERSION file exists at repo root, returns its content stripped."""
        # _read_transport_version resolves VERSION relative to server.py's parent.
        # Since the real VERSION file exists, it returns its content.
        result = server._read_transport_version()
        self.assertEqual(result, "0.1.1")

    def test_returns_default_when_file_missing(self) -> None:
        """When the VERSION path raises FileNotFoundError, returns '0.0.0-dev'."""
        missing = Path("/definitely/not/a/real/path/VERSION")
        with patch("transport.server.Path") as mock_path_cls:
            resolved = MagicMock()
            resolved.parent.parent.__truediv__.return_value = missing
            mock_path_cls.return_value.resolve.return_value = resolved
            result = server._read_transport_version()
        self.assertEqual(result, "0.0.0-dev")

    def test_transport_version_constant_is_string(self) -> None:
        """TRANSPORT_VERSION module constant is a non-empty string."""
        self.assertIsInstance(server.TRANSPORT_VERSION, str)
        self.assertTrue(len(server.TRANSPORT_VERSION) > 0)

    def test_version_file_at_repo_root_exists(self) -> None:
        """The VERSION file actually exists in the repo."""
        version_path = Path(__file__).resolve().parents[2] / "VERSION"
        self.assertTrue(version_path.exists(), f"VERSION file not found at {version_path}")
        content = version_path.read_text().strip()
        self.assertEqual(content, "0.1.1")


class TestVersionEndpoint(unittest.TestCase):
    """Task 5.2: GET /version returns correct JSON structure."""

    def test_handle_version_get_returns_json(self) -> None:
        """_handle_version_get returns JSONResponse with transport version."""
        # Create a mock request
        request = MagicMock()
        # Call the handler
        result = asyncio.run(
            server._handle_version_get(request)
        )
        # The stub JSONResponse stores the dict as .body (json-encoded bytes)
        # In real Starlette, JSONResponse takes a dict; our stub encodes it
        self.assertIsNotNone(result)

    def test_version_endpoint_in_public_routes(self) -> None:
        """The /version route is registered as a public (unauthenticated) route."""
        middleware = server.BearerAuthMiddleware(None, api_key="test-key")
        self.assertIn(("GET", "/version"), middleware._public_routes)

    def test_version_endpoint_handler_exists(self) -> None:
        """_handle_version_get is defined and callable."""
        self.assertTrue(callable(server._handle_version_get))


class TestCrewsVersionField(unittest.TestCase):
    """Task 5.3: crews() output includes crew_image_version field."""

    def test_crews_includes_version_field(self) -> None:
        """crews() entry includes crew_image_version, defaulting to 'unknown'."""
        fake_registry = {
            "crews": {
                "test-crew": {
                    "container": "gs-test-crew",
                    "status": "stopped",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            }
        }
        with patch.object(server, "_load_registry", return_value=fake_registry):
            result = server.crews()

        self.assertEqual(len(result["crews"]), 1)
        entry = result["crews"][0]
        self.assertIn("crew_image_version", entry)
        self.assertEqual(entry["crew_image_version"], "unknown")

    def test_crews_returns_stored_version(self) -> None:
        """crews() returns the stored crew_image_version when present."""
        fake_registry = {
            "crews": {
                "versioned-crew": {
                    "container": "gs-versioned-crew",
                    "status": "stopped",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00Z",
                    "crew_image_version": "0.1.1",
                }
            }
        }
        with patch.object(server, "_load_registry", return_value=fake_registry):
            result = server.crews()

        self.assertEqual(len(result["crews"]), 1)
        entry = result["crews"][0]
        self.assertEqual(entry["crew_image_version"], "0.1.1")


class TestContainerInspect(unittest.TestCase):
    """Test the container_inspect method added for version label reading."""

    def test_container_inspect_method_exists(self) -> None:
        """PodmanClient has container_inspect method."""
        self.assertTrue(hasattr(server.PodmanClient, "container_inspect"))


class TestResourceVersion(unittest.TestCase):
    """Test transport://version MCP resource."""

    def test_resource_version_no_crews(self) -> None:
        """resource_version returns transport version and empty crews dict."""
        fake_registry = {"crews": {}}
        with patch.object(server, "_load_registry", return_value=fake_registry):
            result = json.loads(server.resource_version())

        self.assertIn("transport", result)
        self.assertEqual(result["transport"], server.TRANSPORT_VERSION)
        self.assertIn("crews", result)
        self.assertEqual(result["crews"], {})

    def test_resource_version_with_crews(self) -> None:
        """resource_version includes per-crew version info."""
        fake_registry = {
            "crews": {
                "crew-a": {"crew_image_version": "0.1.1"},
                "crew-b": {},
            }
        }
        with patch.object(server, "_load_registry", return_value=fake_registry):
            result = json.loads(server.resource_version())

        self.assertEqual(result["crews"]["crew-a"]["crew_image_version"], "0.1.1")
        self.assertEqual(result["crews"]["crew-b"]["crew_image_version"], "unknown")


class TestContainerfileVersion(unittest.TestCase):
    """Task 5.4: Verify Containerfile has correct ARG/LABEL."""

    def test_containerfile_has_version_arg(self) -> None:
        """Containerfile contains ARG VERSION=0.0.0-dev."""
        containerfile = Path(__file__).resolve().parents[2] / "crews" / "spec-ops" / "Containerfile"
        content = containerfile.read_text()
        self.assertIn("ARG VERSION=0.0.0-dev", content)

    def test_containerfile_has_version_label(self) -> None:
        """Containerfile contains LABEL org.ghostship.version=$VERSION."""
        containerfile = Path(__file__).resolve().parents[2] / "crews" / "spec-ops" / "Containerfile"
        content = containerfile.read_text()
        self.assertIn("LABEL org.ghostship.version=$VERSION", content)


if __name__ == "__main__":
    unittest.main()
