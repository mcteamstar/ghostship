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

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from tests.unit.helpers import academy, lifecycle, server  # noqa: F401


# ══════════════════════════════════════════════════════════════════════════════
# Registry loading and helpers
# (migrated from TestCrewTypeRegistry + TestCrewTypeHelpers in test_transport.py
#  and from TestLoadCrewTypeRegistry + TestResolveManifestPath in test_crew_types.py)
# ══════════════════════════════════════════════════════════════════════════════


class CrewTypeRegistryTests(unittest.TestCase):
    """Unit tests for _load_composition_registry()."""

    def test_valid_registry_loads_entries(self) -> None:
        """_load_composition_registry() parses a valid registry.json correctly."""
        registry_data = json.dumps({
            "compositions": [
                {"name": "spec-ops", "description": "Default type", "dir": "spec-ops"},
                {"name": "custom", "description": "Custom type", "dir": "custom", "image": "custom:latest"},
            ]
        })
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "registry.json"
            reg_path.write_text(registry_data)

            with (
                patch.object(academy, "_CREW_REGISTRY_PATH", reg_path),
                patch("pathlib.Path.is_dir", return_value=True),
            ):
                result = academy._load_composition_registry()

        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["custom"]["image"], "custom:latest")

    def test_missing_file_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback when file is missing."""
        with patch.object(academy, "_CREW_REGISTRY_PATH", Path("/nonexistent/registry.json")):
            result = academy._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")

    def test_malformed_json_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback for malformed JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json!!!")
            f.flush()
            try:
                with patch.object(academy, "_CREW_REGISTRY_PATH", Path(f.name)):
                    result = academy._load_composition_registry()
                self.assertEqual(list(result.keys()), ["spec-ops"])
            finally:
                Path(f.name).unlink()

    def test_invalid_entries_excluded(self) -> None:
        """_load_composition_registry() skips entries with invalid names."""
        registry_data = json.dumps({
            "compositions": [
                {"name": "INVALID-CAPS", "description": "Bad", "dir": "caps"},
                {"name": "spec-ops", "description": "Good", "dir": "spec-ops"},
            ]
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(registry_data)
            f.flush()
            try:
                with (
                    patch.object(academy, "_CREW_REGISTRY_PATH", Path(f.name)),
                    patch("pathlib.Path.is_dir", return_value=True),
                ):
                    result = academy._load_composition_registry()
                self.assertNotIn("INVALID-CAPS", result)
                self.assertIn("spec-ops", result)
            finally:
                Path(f.name).unlink()

    def test_invalid_entries_excluded_full(self) -> None:
        """Entries with invalid names or missing/empty dirs are excluded."""
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
            patch.object(academy, "_CREW_REGISTRY_PATH", tmp_path),
            patch("pathlib.Path.is_dir", _is_dir_side_effect),
        ):
            result = academy._load_composition_registry()

        # Only "good" should remain — INVALID_NAME is rejected by regex, nodir has empty dir
        self.assertIn("good", result)
        self.assertNotIn("INVALID_NAME", result)
        self.assertNotIn("nodir", result)
        tmp_path.unlink()

    def test_empty_types_list_returns_fallback(self) -> None:
        """Empty compositions list returns fallback."""
        registry_data = {"compositions": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(registry_data, f)
            f.flush()
            tmp_path = Path(f.name)

        with patch.object(academy, "_CREW_REGISTRY_PATH", tmp_path):
            result = academy._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        tmp_path.unlink()

    def test_missing_file_returns_single_fallback(self) -> None:
        """Missing registry file returns single kirocrew fallback."""
        nonexistent = Path("/nonexistent/registry.json")
        with patch.object(academy, "_CREW_REGISTRY_PATH", nonexistent):
            result = academy._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["spec-ops"]["description"], "Default KiroCrew crew type")

    def test_malformed_json_returns_fallback_single(self) -> None:
        """Unparseable JSON returns fallback."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{invalid json!!")
            f.flush()
            tmp_path = Path(f.name)

        with patch.object(academy, "_CREW_REGISTRY_PATH", tmp_path):
            result = academy._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        tmp_path.unlink()

    def test_valid_registry_full(self) -> None:
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

        with (
            patch.object(academy, "_CREW_REGISTRY_PATH", tmp_path),
            patch("pathlib.Path.is_dir", return_value=True),
        ):
            result = academy._load_composition_registry()

        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["custom"]["image"], "my-image:latest")
        self.assertEqual(result["custom"]["description"], "Custom crew type")
        tmp_path.unlink()


class CrewTypeHelpersTests(unittest.TestCase):
    """Unit tests for _resolve_manifest_path() and _resolve_image()."""

    def test_resolve_manifest_path(self) -> None:
        """Returns correct path for a crew type entry."""
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        self.assertEqual(academy._resolve_manifest_path(entry), Path("/crews/spec-ops/manifest.json"))

    def test_resolve_manifest_path_custom_dir(self) -> None:
        """Returns correct path for a custom type."""
        entry = {"name": "custom", "dir": "my-custom-crew"}
        self.assertEqual(academy._resolve_manifest_path(entry), Path("/crews/my-custom-crew/manifest.json"))

    def test_resolve_manifest_path_custom(self) -> None:
        """Returns correct path for a custom dir entry."""
        entry = {"name": "custom", "dir": "my-custom"}
        self.assertEqual(academy._resolve_manifest_path(entry), Path("/crews/my-custom/manifest.json"))

    def test_resolve_image_with_override(self) -> None:
        """Entry with image field returns that image."""
        entry = {"name": "custom", "dir": "custom", "image": "custom:v2"}
        self.assertEqual(academy._resolve_image(entry), "custom:v2")

    def test_resolve_image_with_override_v2(self) -> None:
        """Entry with image field returns that image (v2 registry path)."""
        entry = {"name": "custom", "dir": "custom", "image": "my-registry/custom:v2"}
        self.assertEqual(academy._resolve_image(entry), "my-registry/custom:v2")

    def test_resolve_image_without_override(self) -> None:
        """Entry without image field falls back to KC_IMAGE."""
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        self.assertEqual(academy._resolve_image(entry), academy.KC_IMAGE)

    def test_resolve_image_empty_string_uses_default(self) -> None:
        """Entry with empty image string falls back to KC_IMAGE."""
        entry = {"name": "spec-ops", "dir": "spec-ops", "image": ""}
        self.assertEqual(academy._resolve_image(entry), academy.KC_IMAGE)

    def test_resolve_image_empty_string_falls_back(self) -> None:
        """Entry with empty image string falls back to KC_IMAGE (alias)."""
        entry = {"name": "spec-ops", "dir": "spec-ops", "image": ""}
        self.assertEqual(academy._resolve_image(entry), academy.KC_IMAGE)


# ══════════════════════════════════════════════════════════════════════════════
# launch() with composition parameter
# (migrated from TestLaunchCrewType in test_transport.py
#  and from TestLaunchComposition in test_crew_types.py)
# ══════════════════════════════════════════════════════════════════════════════


class TestLaunchCrewType(unittest.TestCase):
    """Integration tests for launch() with composition parameter.

    launch() is an MCP tool defined in server.py. It calls _resolve_composition()
    (an academy function bound in server's namespace), which reads
    academy.COMPOSITION_REGISTRY. The error-path check in launch() also reads
    server.COMPOSITION_REGISTRY (the at-import binding). Both must be patched
    consistently for these tests to be hermetic.
    """

    def test_launch_with_explicit_composition(self) -> None:
        """launch() with a valid composition resolves image and manifest correctly."""
        test_entry = {"name": "spec-ops", "dir": "spec-ops", "description": "Default"}
        with (
            patch.object(academy, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}),
            patch.object(server, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_finish_crew_setup", return_value={"status": "ready"}) as mock_setup,
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(server, "_wait_gateway", return_value=True),
        ):
            mock_podman = server._get_podman.return_value
            mock_podman.network_create = Mock()
            mock_podman.volume_create = Mock()
            mock_podman.container_create = Mock()
            mock_podman.container_start = Mock()
            mock_podman.container_is_running = Mock(return_value=False)

            result = server.launch("test-crew", composition="spec-ops")

        self.assertEqual(result["status"], "ready")
        # Verify _finish_crew_setup was called with composition and entry
        call_args = mock_setup.call_args
        self.assertEqual(call_args[0][5], "dGVzdA==")  # auth_b64
        self.assertEqual(call_args[0][6], "spec-ops")   # composition
        self.assertEqual(call_args[0][7], test_entry)   # composition_entry

    def test_launch_with_unknown_composition_errors(self) -> None:
        """launch() with unknown composition returns error listing available types."""
        with (
            patch.object(academy, "COMPOSITION_REGISTRY", {"spec-ops": {"name": "spec-ops"}}),
            patch.object(server, "COMPOSITION_REGISTRY", {"spec-ops": {"name": "spec-ops"}}),
        ):
            result = server.launch("test-crew", composition="nonexistent")

        self.assertIn("error", result)
        self.assertIn("nonexistent", result["error"])
        self.assertIn("spec-ops", result["error"])

    def test_launch_uses_resolved_image_for_container(self) -> None:
        """launch() passes the resolved image to container_create."""
        test_entry = {"name": "custom", "dir": "custom", "description": "Custom", "image": "custom:v3"}
        with (
            patch.object(academy, "COMPOSITION_REGISTRY", {"custom": test_entry}),
            patch.object(server, "COMPOSITION_REGISTRY", {"custom": test_entry}),
            patch.object(server, "_get_podman") as mock_get_podman,
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_finish_crew_setup", return_value={"status": "ready"}),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
            patch.object(server, "_wait_gateway", return_value=True),
        ):
            mock_podman = Mock()
            mock_podman.container_is_running = Mock(return_value=False)
            mock_get_podman.return_value = mock_podman

            server.launch("my-crew", composition="custom")

        # Verify container_create was called with the custom image
        mock_podman.container_create.assert_called_once()
        call_kwargs = mock_podman.container_create.call_args[1]
        self.assertEqual(call_kwargs["image"], "custom:v3")

    def test_launch_unknown_composition_returns_error(self) -> None:
        """Unknown composition returns error listing available types."""
        result = server.launch(crew_id="test-crew", composition="nonexistent")
        self.assertIn("error", result)
        self.assertIn("nonexistent", result["error"])
        self.assertIn("Available:", result["error"])

    def test_launch_with_valid_composition_uses_correct_image(self) -> None:
        """launch() with explicit composition uses the resolved image."""
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

        with (
            patch.object(academy, "COMPOSITION_REGISTRY", custom_registry),
            patch.object(server, "COMPOSITION_REGISTRY", custom_registry),
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
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
        """launch() with default composition uses KC_IMAGE."""
        mock_podman = MagicMock()
        mock_podman.container_is_running.return_value = False
        default_registry = {
            "spec-ops": {
                "name": "spec-ops",
                "dir": "spec-ops",
                "description": "Default KiroCrew crew type",
            }
        }

        with (
            patch.object(academy, "COMPOSITION_REGISTRY", default_registry),
            patch.object(server, "COMPOSITION_REGISTRY", default_registry),
            patch.object(server, "_get_podman", return_value=mock_podman),
            patch.object(lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(lifecycle, "_save_registry"),
            patch.object(server, "_save_registry"),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(lifecycle, "_wait_gateway", return_value=True),
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
        self.assertEqual(call_kwargs[1]["image"], academy.KC_IMAGE)


# ══════════════════════════════════════════════════════════════════════════════
# compositions MCP tool
# (migrated from TestCrewTypesTool in test_transport.py
#  and from TestCompositionsResource in test_crew_types.py)
# ══════════════════════════════════════════════════════════════════════════════


class TestCrewTypesTool(unittest.TestCase):
    """Test for the compositions discovery tool.

    resource_compositions() is defined in server.py and reads COMPOSITION_REGISTRY
    from server's namespace. Patch ``server.COMPOSITION_REGISTRY`` at the call site.
    """

    def test_compositions_returns_registry_entries(self) -> None:
        """resource_compositions() returns text with name and description from the registry."""
        test_registry = {
            "spec-ops": {"name": "spec-ops", "dir": "spec-ops", "description": "Default KiroCrew"},
            "custom": {"name": "custom", "dir": "custom", "description": "Custom crew type"},
        }
        with patch.object(server, "COMPOSITION_REGISTRY", test_registry):
            result = server.resource_compositions()

        self.assertIsInstance(result, str)
        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertIn("Default KiroCrew", result)
        self.assertIn("Custom crew type", result)

    def test_compositions_returns_registry_entries_with_image(self) -> None:
        """resource_compositions() returns text with name, description, and image."""
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
        """Default registry always contains spec-ops."""
        result = server.resource_compositions()
        self.assertIn("spec-ops", result)


# ══════════════════════════════════════════════════════════════════════════════
# _substitute_env_vars
# (migrated from SubstituteEnvVarsTests in test_transport.py)
# ══════════════════════════════════════════════════════════════════════════════


class SubstituteEnvVarsTests(unittest.TestCase):
    """Unit tests for _substitute_env_vars (trn-68)."""

    def test_string_substitution(self) -> None:
        """String values have ${VAR} replaced from env."""
        result = academy._substitute_env_vars("Bearer ${TOKEN}", {"TOKEN": "abc123"})
        self.assertEqual(result, "Bearer abc123")

    def test_nested_dict_substitution(self) -> None:
        """Recurses into nested dicts."""
        result = academy._substitute_env_vars(
            {"headers": {"Authorization": "Bearer ${TOKEN}"}},
            {"TOKEN": "secret"},
        )
        self.assertEqual(result["headers"]["Authorization"], "Bearer secret")

    def test_list_substitution(self) -> None:
        """Recurses into lists."""
        result = academy._substitute_env_vars(["${A}", "${B}"], {"A": "alpha", "B": "beta"})
        self.assertEqual(result, ["alpha", "beta"])

    def test_missing_var_writes_literal_and_warns(self) -> None:
        """Missing variable writes literal ${VAR} and logs a warning."""
        with self.assertLogs("transport", level="WARNING") as log_ctx:
            result = academy._substitute_env_vars("Bearer ${ABSENT_VAR}", {})
        self.assertEqual(result, "Bearer ${ABSENT_VAR}")
        self.assertTrue(any("ABSENT_VAR" in m for m in log_ctx.output))

    def test_non_string_passthrough(self) -> None:
        """Non-string values (int, None, bool) pass through unchanged."""
        self.assertEqual(academy._substitute_env_vars(42, {}), 42)
        self.assertIsNone(academy._substitute_env_vars(None, {}))
        self.assertTrue(academy._substitute_env_vars(True, {}))


# ══════════════════════════════════════════════════════════════════════════════
# _validate_academy — agent schema, manifest cross-ref, order template checks
# (migrated from test_academy_validation.py — patch targets already correct,
#  stale lifecycle/server patches removed)
# ══════════════════════════════════════════════════════════════════════════════


def _write(dir_path: Path, name: str, content: str) -> None:
    (dir_path / name).write_text(content, encoding="utf-8")


class _AcademyValidationBase(unittest.TestCase):
    """Provides a fully isolated, empty academy the subclass fills in."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.agents_dir = root / "agents"
        self.orders_dir = root / "orders"
        self.skills_dir = root / "skills"
        self.steering_dir = root / "steering"
        for d in (self.agents_dir, self.orders_dir, self.skills_dir, self.steering_dir):
            d.mkdir()

        # By default no crew type is registered (no manifest cross-ref) so the
        # schema/order tests are undisturbed. Manifest tests override these.
        self._patchers = [
            patch.object(academy, "_AGENTS_DIR", self.agents_dir),
            patch.object(academy, "_resolve_orders_dir", return_value=self.orders_dir),
            patch.object(academy, "COMPOSITION_REGISTRY", {}),
            # Point the hardcoded pool literals at our empty temp dirs.
            patch.object(academy, "Path", self._path_shim()),
        ]
        for p in self._patchers:
            p.start()

    def _path_shim(self):
        """Return a Path replacement that redirects /skills and /steering to
        our temp pools and passes everything else through to the real Path."""
        real_path = Path
        skills = self.skills_dir
        steering = self.steering_dir

        def shim(arg):
            if arg == "/skills":
                return skills
            if arg == "/steering":
                return steering
            return real_path(arg)

        return shim

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()
        self._tmp.cleanup()


class TestAgentJsonSchema(_AcademyValidationBase):
    def test_valid_agent_no_warning(self) -> None:
        """Task 2.1: valid agent JSON with all required fields → no warning."""
        _write(
            self.agents_dir,
            "ghost.json",
            json.dumps({"name": "ghost", "description": "d", "tools": ["a"]}),
        )
        warnings = academy._validate_academy()
        self.assertEqual(warnings, [])

    def test_missing_tools_field_warns(self) -> None:
        """Task 2.2: agent JSON missing `tools` → a warning naming the field."""
        _write(
            self.agents_dir,
            "ghost.json",
            json.dumps({"name": "ghost", "description": "d"}),
        )
        warnings = academy._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("ghost.json", warnings[0])
        self.assertIn("tools", warnings[0])

    def test_malformed_json_warns(self) -> None:
        """Task 2.3: agent JSON that is not valid JSON → a warning."""
        _write(self.agents_dir, "broken.json", "{ this is not json ")
        warnings = academy._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("broken.json", warnings[0])
        self.assertIn("JSON", warnings[0])


class TestManifestCrossReference(_AcademyValidationBase):
    def _register_crew(self, manifest: dict) -> None:
        academy.COMPOSITION_REGISTRY.clear()
        academy.COMPOSITION_REGISTRY["spec-ops"] = {"name": "spec-ops", "dir": "spec-ops"}
        self._manifest_patch = patch.object(
            academy, "_load_crew_manifest", return_value=manifest
        )
        self._manifest_patch.start()
        self.addCleanup(self._manifest_patch.stop)

    def test_unknown_agent_name_warns(self) -> None:
        """Task 2.4: manifest referencing an unknown agent name → a warning."""
        # Only ghost.json exists in the pool; manifest asks for nonexistent.json.
        _write(
            self.agents_dir,
            "ghost.json",
            json.dumps({"name": "ghost", "description": "d", "tools": []}),
        )
        self._register_crew(
            {"agents": ["ghost.json", "nonexistent.json"], "skills": "*", "steering": "*"}
        )
        warnings = academy._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("nonexistent.json", warnings[0])
        self.assertIn("spec-ops", warnings[0])

    def test_wildcard_manifest_no_cross_ref_warning(self) -> None:
        """Task 2.5: manifest of `"*"` for all sections → no cross-ref warnings."""
        _write(
            self.agents_dir,
            "ghost.json",
            json.dumps({"name": "ghost", "description": "d", "tools": []}),
        )
        self._register_crew({"agents": "*", "skills": "*", "steering": "*"})
        warnings = academy._validate_academy()
        self.assertEqual(warnings, [])


class TestOrderTemplateFrontMatter(_AcademyValidationBase):
    def test_valid_order_no_warning(self) -> None:
        """Task 2.6: valid front-matter + placeholder → no warning."""
        _write(
            self.orders_dir,
            "sdd.md",
            '---\ndescription: "x"\n---\nBody with a {{PLACEHOLDER}} token.\n',
        )
        warnings = academy._validate_academy()
        self.assertEqual(warnings, [])

    def test_missing_placeholder_warns(self) -> None:
        """Task 2.7: order template missing a {{...}} placeholder → a warning."""
        _write(
            self.orders_dir,
            "sdd.md",
            '---\ndescription: "x"\n---\nBody with no placeholder at all.\n',
        )
        warnings = academy._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("sdd.md", warnings[0])
        self.assertIn("placeholder", warnings[0])


if __name__ == "__main__":
    unittest.main()
