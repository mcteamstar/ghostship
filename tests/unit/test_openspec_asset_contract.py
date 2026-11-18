from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dependency_check as check

EXPECTED_OPENSPEC_VERSION = "2.1.0"


def openspec_inventory():
    return {
        "review_owner": "Test maintainers",
        "components": [{
            "id": "openspec-cli",
            "name": "OpenSpec CLI",
            "category": "development CLI",
            "declarations": [{
                "kind": "npm",
                "path": "crews/spec-ops/Containerfile",
                "package": "@fission-ai/openspec",
            }],
            "source": {"type": "npm", "package": "@fission-ai/openspec"},
            "compatibility": {"status": "unknown", "evidence": None},
            "review": {
                "owner": "Test maintainers",
                "last_reviewed": None,
                "outcome": "not-reviewed",
                "next_review": None,
                "evidence": None,
            },
        }],
    }


class OpenSpecAssetContractTests(unittest.TestCase):
    def test_repository_cli_pin_matches_all_six_academy_skills(self):
        errors = check.validate_openspec_assets(check.ROOT)
        self.assertEqual(errors, [])

        containerfile = (check.ROOT / "crews/spec-ops/Containerfile").read_text(encoding="utf-8")
        self.assertIn(f"@fission-ai/openspec@{EXPECTED_OPENSPEC_VERSION}", containerfile)

    def _write_fixture(self, root: Path, cli_version: str, skill_versions: dict[str, str], stale_skill: str | None = None):
        containerfile = root / "crews/spec-ops/Containerfile"
        containerfile.parent.mkdir(parents=True)
        containerfile.write_text(
            f"RUN npm install -g @fission-ai/openspec@{cli_version}\n",
            encoding="utf-8",
        )
        for skill_name in check.OPENSPEC_SKILLS:
            skill_file = root / "academy/skills" / skill_name / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            invocation = "/opsx:apply" if skill_name == stale_skill else ""
            skill_file.write_text(
                "---\n"
                f"name: {skill_name}\n"
                "metadata:\n"
                f"  generatedBy: \"{skill_versions[skill_name]}\"\n"
                "---\n"
                f"{invocation}\n",
                encoding="utf-8",
            )

    def test_inventory_rejects_a_skill_version_mismatch_and_v1_command_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_versions = {name: EXPECTED_OPENSPEC_VERSION for name in check.OPENSPEC_SKILLS}
            skill_versions["openspec-apply-change"] = "1.14.3"
            self._write_fixture(root, EXPECTED_OPENSPEC_VERSION, skill_versions, stale_skill="openspec-apply-change")

            errors, _ = check.validate_inventory(root, openspec_inventory())

        self.assertIn(
            "openspec-skills: openspec-apply-change generatedBy '1.14.3' does not match CLI pin '2.1.0'",
            errors,
        )
        self.assertIn("openspec-skills: openspec-apply-change still references v1 command files", errors)

    def test_inventory_rejects_a_non_exact_cli_pin_and_cli_skill_version_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_versions = {name: EXPECTED_OPENSPEC_VERSION for name in check.OPENSPEC_SKILLS}
            self._write_fixture(root, "^2.1.0", skill_versions)

            errors, _ = check.validate_inventory(root, openspec_inventory())

        self.assertIn("openspec-cli: expected an exact semantic version, found '^2.1.0'", errors)
        self.assertTrue(any("does not match CLI pin '^2.1.0'" in error for error in errors))

    def test_inventory_rejects_skill_version_after_cli_pin_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skill_versions = {name: EXPECTED_OPENSPEC_VERSION for name in check.OPENSPEC_SKILLS}
            self._write_fixture(root, "2.2.0", skill_versions)

            errors, _ = check.validate_inventory(root, openspec_inventory())

        self.assertTrue(any("does not match CLI pin '2.2.0'" in error for error in errors))
