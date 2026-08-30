"""Tests for Academy startup validation (trn-76-academy-validation).

Covers _validate_academy():
  - Agent JSON schema checks (valid, missing field, malformed JSON)
  - Manifest cross-reference against the agents pool (unknown name, "*")
  - Order template front-matter and {{...}} placeholder checks

Each test isolates the three pools by patching the module-level path handles
(_AGENTS_DIR, _resolve_orders_dir) and the manifest/registry surface, and by
pointing the /skills and /steering pools at empty temp dirs so unrelated
checks stay silent.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.unit.test_file_transfer import server
import transport.academy as academy
import transport.lifecycle as lifecycle


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
            patch.object(lifecycle, "_AGENTS_DIR", self.agents_dir),
            patch.object(server, "_AGENTS_DIR", self.agents_dir),
            patch.object(academy, "_resolve_orders_dir", return_value=self.orders_dir),
            patch.object(lifecycle, "_resolve_orders_dir", return_value=self.orders_dir),
            patch.object(server, "_resolve_orders_dir", return_value=self.orders_dir),
            patch.object(academy, "COMPOSITION_REGISTRY", {}),
            patch.object(lifecycle, "COMPOSITION_REGISTRY", {}),
            patch.object(server, "COMPOSITION_REGISTRY", {}),
            # Point the hardcoded pool literals at our empty temp dirs.
            patch.object(academy, "Path", self._path_shim()),
            patch.object(lifecycle, "Path", self._path_shim()),
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
        warnings = server._validate_academy()
        self.assertEqual(warnings, [])

    def test_missing_tools_field_warns(self) -> None:
        """Task 2.2: agent JSON missing `tools` → a warning naming the field."""
        _write(
            self.agents_dir,
            "ghost.json",
            json.dumps({"name": "ghost", "description": "d"}),
        )
        warnings = server._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("ghost.json", warnings[0])
        self.assertIn("tools", warnings[0])

    def test_malformed_json_warns(self) -> None:
        """Task 2.3: agent JSON that is not valid JSON → a warning."""
        _write(self.agents_dir, "broken.json", "{ this is not json ")
        warnings = server._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("broken.json", warnings[0])
        self.assertIn("JSON", warnings[0])


class TestManifestCrossReference(_AcademyValidationBase):
    def _register_crew(self, manifest: dict) -> None:
        server.COMPOSITION_REGISTRY.clear()
        server.COMPOSITION_REGISTRY["spec-ops"] = {"name": "spec-ops", "dir": "spec-ops"}
        lifecycle.COMPOSITION_REGISTRY.clear()
        lifecycle.COMPOSITION_REGISTRY["spec-ops"] = {"name": "spec-ops", "dir": "spec-ops"}
        academy.COMPOSITION_REGISTRY.clear()
        academy.COMPOSITION_REGISTRY["spec-ops"] = {"name": "spec-ops", "dir": "spec-ops"}
        self._manifest_patch = patch.object(
            academy, "_load_crew_manifest", return_value=manifest
        )
        self._manifest_patch2 = patch.object(
            lifecycle, "_load_crew_manifest", return_value=manifest
        )
        self._manifest_patch3 = patch.object(
            server, "_load_crew_manifest", return_value=manifest
        )
        self._manifest_patch.start()
        self._manifest_patch2.start()
        self._manifest_patch3.start()
        self.addCleanup(self._manifest_patch.stop)
        self.addCleanup(self._manifest_patch2.stop)
        self.addCleanup(self._manifest_patch3.stop)

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
        warnings = server._validate_academy()
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
        warnings = server._validate_academy()
        self.assertEqual(warnings, [])


class TestOrderTemplateFrontMatter(_AcademyValidationBase):
    def test_valid_order_no_warning(self) -> None:
        """Task 2.6: valid front-matter + placeholder → no warning."""
        _write(
            self.orders_dir,
            "sdd.md",
            '---\ndescription: "x"\n---\nBody with a {{PLACEHOLDER}} token.\n',
        )
        warnings = server._validate_academy()
        self.assertEqual(warnings, [])

    def test_missing_placeholder_warns(self) -> None:
        """Task 2.7: order template missing a {{...}} placeholder → a warning."""
        _write(
            self.orders_dir,
            "sdd.md",
            '---\ndescription: "x"\n---\nBody with no placeholder at all.\n',
        )
        warnings = server._validate_academy()
        self.assertEqual(len(warnings), 1)
        self.assertIn("sdd.md", warnings[0])
        self.assertIn("placeholder", warnings[0])


if __name__ == "__main__":
    unittest.main()
