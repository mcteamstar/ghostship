"""Tests for the crew-types feature (srv-61-crew-types).

Covers:
  - _load_composition_registry() with valid, missing, and malformed inputs
  - _resolve_manifest_path() and _resolve_image() helpers
  - launch() with explicit composition and with unknown composition
  - compositions() discovery tool
"""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch, MagicMock

from tests.unit.test_file_transfer import server


class TestLoadCrewTypeRegistry(unittest.TestCase):
    """Task 8.1: Unit tests for _load_composition_registry()."""

    def test_valid_registry(self) -> None:
        """Valid registry file returns correct name→entry mapping."""
        registry_data = {
            "compositions": [
                {
                    "name": "spec-ops",
                    "description": "Default crew",
                    "dir": "spec-ops",
                },
                {
                    "name": "custom",
                    "description": "Custom crew type",
                    "dir": "custom",
                    "image": "my-image:latest",
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            tmp_path = Path(f.name)

        # Patch the registry path and ensure both dirs "exist"
        with (
            patch.object(server, "_CREW_REGISTRY_PATH", tmp_path),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = server._load_composition_registry()

        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["custom"]["image"], "my-image:latest")
        self.assertEqual(result["custom"]["description"], "Custom crew type")
        tmp_path.unlink()

    def test_missing_file_returns_fallback(self) -> None:
        """Missing registry file returns single kirocrew fallback."""
        nonexistent = Path("/nonexistent/registry.json")
        with patch.object(server, "_CREW_REGISTRY_PATH", nonexistent):
            result = server._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["spec-ops"]["description"], "Default KiroCrew crew type")

    def test_malformed_json_returns_fallback(self) -> None:
        """Unparseable JSON returns fallback."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json!!")
            f.flush()
            tmp_path = Path(f.name)

        with patch.object(server, "_CREW_REGISTRY_PATH", tmp_path):
            result = server._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        tmp_path.unlink()

    def test_invalid_entries_excluded(self) -> None:
        """Entries with invalid names or missing dirs are excluded."""
        registry_data = {
            "compositions": [
                {
                    "name": "INVALID_NAME",  # uppercase not allowed
                    "description": "Bad",
                    "dir": "invalid",
                },
                {
                    "name": "good",
                    "description": "Good entry",
                    "dir": "gooddir",
                },
                {
                    "name": "nodir",
                    "description": "Missing dir field",
                    "dir": "",
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            tmp_path = Path(f.name)

        def _is_dir_side_effect(self: Path) -> bool:
            return "gooddir" in str(self)

        with (
            patch.object(server, "_CREW_REGISTRY_PATH", tmp_path),
            patch("pathlib.Path.is_dir", _is_dir_side_effect),
        ):
            result = server._load_composition_registry()

        # Only "good" should remain — INVALID_NAME is rejected by regex, nodir has empty dir
        self.assertIn("good", result)
        self.assertNotIn("INVALID_NAME", result)
        self.assertNotIn("nodir", result)
        tmp_path.unlink()

    def test_empty_types_list_returns_fallback(self) -> None:
        """Empty types list returns fallback."""
        registry_data = {"compositions": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            tmp_path = Path(f.name)

        with patch.object(server, "_CREW_REGISTRY_PATH", tmp_path):
            result = server._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        tmp_path.unlink()


class TestResolveManifestPath(unittest.TestCase):
    """Task 8.2: Unit tests for _resolve_manifest_path() and _resolve_image()."""

    def test_resolve_manifest_path(self) -> None:
        """Returns correct path for a crew type entry."""
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        result = server._resolve_manifest_path(entry)
        self.assertEqual(result, Path("/crews/spec-ops/manifest.json"))

    def test_resolve_manifest_path_custom(self) -> None:
        """Returns correct path for a custom type."""
        entry = {"name": "custom", "dir": "my-custom"}
        result = server._resolve_manifest_path(entry)
        self.assertEqual(result, Path("/crews/my-custom/manifest.json"))

    def test_resolve_image_with_override(self) -> None:
        """Entry with image field returns that image."""
        entry = {"name": "custom", "dir": "custom", "image": "my-registry/custom:v2"}
        result = server._resolve_image(entry)
        self.assertEqual(result, "my-registry/custom:v2")

    def test_resolve_image_without_override(self) -> None:
        """Entry without image field falls back to KC_IMAGE."""
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        result = server._resolve_image(entry)
        self.assertEqual(result, server.KC_IMAGE)

    def test_resolve_image_empty_string_falls_back(self) -> None:
        """Entry with empty image string falls back to KC_IMAGE."""
        entry = {"name": "spec-ops", "dir": "spec-ops", "image": ""}
        result = server._resolve_image(entry)
        self.assertEqual(result, server.KC_IMAGE)


class TestLaunchComposition(unittest.TestCase):
    """Task 8.3 & 8.4: Integration tests for launch() with composition."""

    def test_launch_unknown_composition_returns_error(self) -> None:
        """Task 8.4: Unknown composition returns error listing available types."""
        result = server.launch(crew_id="test-crew", composition="nonexistent")
        self.assertIn("error", result)
        self.assertIn("nonexistent", result["error"])
        self.assertIn("Available:", result["error"])

    def test_launch_with_valid_composition_uses_correct_image(self) -> None:
        """Task 8.3: launch() with explicit composition uses the resolved image."""
        custom_entry = {
            "name": "custom",
            "dir": "custom",
            "description": "Custom type",
            "image": "custom-image:v1",
        }
        custom_registry = {
            "spec-ops": {
                "name": "spec-ops",
                "dir": "spec-ops",
                "description": "Default",
            },
            "custom": custom_entry,
        }

        mock_podman = MagicMock()
        mock_podman.container_is_running.return_value = False

        # Mock everything to isolate the composition resolution and image usage
        with (
            patch.object(server, "COMPOSITION_REGISTRY", custom_registry),
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(
                server, "_finish_crew_setup",
                return_value={"crew_id": "test", "status": "ready"},
            ) as mock_finish,
        ):
            result = server.launch(crew_id="test", composition="custom")

        self.assertEqual(result["status"], "ready")
        # Verify the container was created with the custom image
        mock_podman.container_create.assert_called_once()
        call_kwargs = mock_podman.container_create.call_args
        self.assertEqual(call_kwargs[1]["image"], "custom-image:v1")

    def test_launch_default_composition_uses_kc_image(self) -> None:
        """Task 8.3: launch() with default composition uses KC_IMAGE."""
        mock_podman = MagicMock()
        mock_podman.container_is_running.return_value = False

        with (
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(
                server, "_finish_crew_setup",
                return_value={"crew_id": "test", "status": "ready"},
            ),
        ):
            result = server.launch(crew_id="test")

        self.assertEqual(result["status"], "ready")
        mock_podman.container_create.assert_called_once()
        call_kwargs = mock_podman.container_create.call_args
        self.assertEqual(call_kwargs[1]["image"], server.KC_IMAGE)


class TestCompositionsResource(unittest.TestCase):
    """Task 8.5: Test transport://compositions resource returns expected text."""

    def test_compositions_returns_registry_entries(self) -> None:
        """resource_compositions() returns text with name and description for each entry."""
        mock_registry = {
            "spec-ops": {
                "name": "spec-ops",
                "dir": "spec-ops",
                "description": "Default KiroCrew crew type",
            },
            "custom": {
                "name": "custom",
                "dir": "custom",
                "description": "A custom crew type",
                "image": "custom:latest",
            },
        }
        with patch.object(server, "COMPOSITION_REGISTRY", mock_registry):
            result = server.resource_compositions()

        self.assertIsInstance(result, str)
        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertIn("Default KiroCrew crew type", result)
        self.assertIn("A custom crew type", result)
        self.assertIn("custom:latest", result)

    def test_compositions_default_registry_has_kirocrew(self) -> None:
        """Default registry always contains kirocrew."""
        result = server.resource_compositions()
        self.assertIn("spec-ops", result)


if __name__ == "__main__":
    unittest.main()
