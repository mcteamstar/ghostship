from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import dependency_check as check


def component(component_id, declarations, source):
    return {
        "id": component_id,
        "declarations": declarations,
        "source": source,
        "compatibility": {"status": "unknown", "evidence": None},
        "review": {"owner": "Test maintainers", "last_reviewed": None, "outcome": "not-reviewed",
                    "next_review": None, "evidence": None},
    }


def inventory(components):
    return {"review_owner": "Test maintainers", "components": components}


class DependencyCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_reports_dependency_input_missing_from_inventory(self):
        (self.root / "requirements.txt").write_text("alpha==1.0\n", encoding="utf-8")

        errors, _ = check.validate_inventory(self.root, inventory([]))

        self.assertTrue(any("missing dependency input from inventory: requirement:requirements.txt:alpha" in e for e in errors))

    def test_reports_stale_inventory_locator_when_source_changes(self):
        (self.root / "requirements.txt").write_text("beta>=2,<3\n", encoding="utf-8")
        old = component("alpha", [{"kind": "requirement", "path": "requirements.txt", "package": "alpha"}],
                        {"type": "pypi", "package": "alpha"})

        errors, _ = check.validate_inventory(self.root, inventory([old]))

        self.assertTrue(any("missing dependency input from inventory" in e and ":beta" in e for e in errors))
        self.assertTrue(any("stale inventory declaration" in e and ":alpha" in e for e in errors))

    def test_reports_broken_derived_parent_link(self):
        (self.root / "Containerfile").write_text("FROM scratch\n", encoding="utf-8")
        derived = component("child", [{"kind": "derived", "path": "Containerfile", "parents": ["missing-parent"]}],
                            {"type": "derived", "parent": "missing-parent"})

        errors, _ = check.validate_inventory(self.root, inventory([derived]))

        self.assertIn("child: broken derived link to missing-parent", errors)

    def test_reports_malformed_component_as_validation_error(self):
        errors, _ = check.validate_inventory(self.root, inventory([None]))

        self.assertTrue(any("invalid inventory structure" in error for error in errors))

    def test_reports_missing_component_id_and_source(self):
        malformed = component("alpha", [], {})
        malformed.pop("id")

        errors, _ = check.validate_inventory(self.root, inventory([malformed]))

        self.assertTrue(any("missing or invalid id" in error for error in errors))
        self.assertTrue(any("missing or unsupported upstream source" in error for error in errors))

    def test_discovers_ci_python_stream_and_ignores_local_environments(self):
        workflow = self.root / ".github" / "workflows" / "test.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text('uses: actions/setup-python@v7\npython-version: "3.12"\n', encoding="utf-8")
        local = self.root / ".venv" / "requirements.txt"
        local.parent.mkdir()
        local.write_text("untracked-local-package==9.9\n", encoding="utf-8")

        actual = check.discover_inputs(self.root)

        self.assertEqual(actual["github_python_runtime:.github/workflows/test.yml:python"], "3.12")
        self.assertFalse(any("untracked-local-package" in key for key in actual))

    def test_keeps_ranges_and_branch_refs_distinct_from_installed_versions(self):
        (self.root / "requirements.txt").write_text("alpha>=1,<2\n", encoding="utf-8")
        (self.root / "Containerfile").write_text(
            'ARG AGENTS_URL="https://github.com/example/assets.git"\nARG AGENTS_REF="main"\n',
            encoding="utf-8",
        )
        components = [
            component("alpha", [{"kind": "requirement", "path": "requirements.txt", "package": "alpha"}],
                      {"type": "pypi", "package": "alpha"}),
            component("assets", [{"kind": "git_ref", "path": "Containerfile", "name": "shared-agent-assets"}],
                      {"type": "github_ref", "repository": "example/assets"}),
        ]

        errors, actual = check.validate_inventory(self.root, inventory(components))

        self.assertEqual(errors, [])
        requirement = actual["requirement:requirements.txt:alpha"]
        branch = actual["git_ref:Containerfile:shared-agent-assets"]
        self.assertEqual(requirement, ">=1,<2")
        self.assertEqual(check.classify_declaration("requirement", requirement), "range")
        self.assertEqual(check.classify_declaration("git_ref", branch), "unpinned branch or tag ref")
        self.assertEqual(check.classify_declaration(
            "git_ref", {"ref": "3ca5a8822a9622012a7cad9a2383e88e7919ab1d"}), "commit ref")
        self.assertTrue(all("installed_version" not in item for item in components))

    def test_registry_fixtures_cover_npm_pypi_image_and_release_candidates(self):
        def fetch(url, headers=None):
            if "pypi.org" in url:
                return {"info": {"version": "2.0rc1"}, "releases": {
                    "1.9.0": [{"yanked": False}], "2.0rc1": [{"yanked": False}]}}
            if "registry.npmjs.org" in url:
                return {"dist-tags": {"latest": "1.2.0", "next": "2.0.0-beta.1"}}
            if "hub.docker.com" in url:
                return {"results": [{"name": "3.12.10-slim"}, {"name": "3.12.11-rc.1-slim"}]}
            if "api.github.com" in url:
                return [
                    {"tag_name": "v1.9.0", "draft": False, "prerelease": False},
                    {"tag_name": "v2.0.0-rc.1", "draft": False, "prerelease": True},
                ]
            raise AssertionError("unexpected fixture URL: " + url)

        pypi = check.lookup_source({"type": "pypi", "package": "alpha"}, True, fetch=fetch)
        npm = check.lookup_source({"type": "npm", "package": "@scope/pkg"}, True, fetch=fetch)
        image = check.lookup_source({"type": "dockerhub_image", "repository": "library/python",
                                     "tag_regex": r"3\.12\.\d+(?:-rc\.\d+)?-slim"}, True, fetch=fetch)
        release = check.lookup_source({"type": "github_release", "repository": "example/project"}, True, fetch=fetch)

        self.assertEqual((pypi["candidate"], pypi["prerelease"]), ("1.9.0", "2.0rc1"))
        self.assertEqual((npm["candidate"], npm["prerelease"]), ("1.2.0", "2.0.0-beta.1"))
        self.assertEqual((image["candidate"], image["prerelease"]), ("3.12.10-slim", "3.12.11-rc.1-slim"))
        self.assertEqual((release["candidate"], release["prerelease"]), ("v1.9.0", "v2.0.0-rc.1"))
        self.assertEqual(check.newest(["v0.9.9", "0.12.0"]), "0.12.0")

    def test_pypi_candidate_survives_when_only_some_release_files_are_yanked(self):
        def fetch(url, headers=None):
            return {"releases": {
                "1.9.0": [{"yanked": True}, {"yanked": False}],
                "2.0.0": [{"yanked": True}, {"yanked": True}],
            }}

        result = check.lookup_source({"type": "pypi", "package": "alpha"}, fetch=fetch)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["candidate"], "1.9.0")

    def test_successful_lookup_without_stable_candidate_is_not_a_failure(self):
        def fetch(url, headers=None):
            return {"info": {"version": "2.0rc1"}, "releases": {
                "1.0.0": [{"yanked": True}], "2.0rc1": [{"yanked": False}]}}

        stable_only = check.lookup_source({"type": "pypi", "package": "alpha"}, fetch=fetch)
        with_prerelease = check.lookup_source({"type": "pypi", "package": "alpha"},
                                              include_prerelease=True, fetch=fetch)

        self.assertEqual(stable_only["status"], "ok")
        self.assertIsNone(stable_only["candidate"])
        self.assertIsNone(stable_only["prerelease"])
        self.assertIn("no matching stable candidate", stable_only["detail"])
        self.assertEqual(with_prerelease["status"], "ok")
        self.assertIsNone(with_prerelease["candidate"])
        self.assertEqual(with_prerelease["prerelease"], "2.0rc1")

    def test_check_reports_prerelease_only_result_as_complete(self):
        (self.root / "requirements.txt").write_text("alpha==1.0\n", encoding="utf-8")
        dependency = component(
            "alpha",
            [{"kind": "requirement", "path": "requirements.txt", "package": "alpha"}],
            {"type": "pypi", "package": "alpha"},
        )
        inventory_path = self.root / "inventory.yaml"
        inventory_path.write_text(check.yaml.safe_dump(inventory([dependency])), encoding="utf-8")
        responses_path = self.root / "responses.json"
        responses_path.write_text(check.json.dumps({
            "pypi:alpha": {"status": "ok", "candidate": None, "prerelease": "2.0rc1",
                            "detail": "no stable candidate matched"},
        }), encoding="utf-8")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            status = check.command_check(self.root, inventory_path, True, responses_path)

        self.assertEqual(status, 0)
        self.assertIn("no stable candidate (prerelease 2.0rc1)", output.getvalue())
        self.assertIn("Result: complete", output.getvalue())

    def test_check_reports_capped_pagination_as_incomplete(self):
        (self.root / "requirements.txt").write_text("alpha==1.0\n", encoding="utf-8")
        dependency = component(
            "alpha",
            [{"kind": "requirement", "path": "requirements.txt", "package": "alpha"}],
            {"type": "pypi", "package": "alpha"},
        )
        inventory_path = self.root / "inventory.yaml"
        inventory_path.write_text(check.yaml.safe_dump(inventory([dependency])), encoding="utf-8")
        responses_path = self.root / "responses.json"
        responses_path.write_text(check.json.dumps({
            "pypi:alpha": {"status": "partial", "candidate": "1.2.0", "prerelease": None,
                            "detail": "pagination cap reached"},
        }), encoding="utf-8")
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            status = check.command_check(self.root, inventory_path, False, responses_path)

        self.assertEqual(status, 1)
        self.assertIn("partial scan: 1.2.0", output.getvalue())
        self.assertIn("Result: INCOMPLETE", output.getvalue())

    def test_dockerhub_and_github_releases_follow_bounded_pagination(self):
        docker_calls = []

        def docker_fetch(url):
            docker_calls.append(url)
            if "page=2" in url:
                return {"results": [{"name": "2.0.0"}], "next": None}
            return {"results": [{"name": "1.0.0"}], "next": "?page=2"}

        image = check.lookup_source({"type": "dockerhub_image", "repository": "library/example",
                                     "tag_regex": r"\d+\.\d+\.\d+"}, fetch=docker_fetch)
        self.assertEqual(image["candidate"], "2.0.0")
        self.assertEqual(len(docker_calls), 2)

        release_calls = []

        def release_fetch(url, headers=None):
            release_calls.append(url)
            if "page=2" in url:
                return [{"tag_name": "v2.0.0", "draft": False, "prerelease": False}]
            return [{"tag_name": f"v1.0.{index}", "draft": False, "prerelease": False}
                    for index in range(check.PAGE_SIZE)]

        release = check.lookup_source({"type": "github_release", "repository": "example/project"},
                                      fetch=release_fetch)
        self.assertEqual(release["candidate"], "v2.0.0")
        self.assertEqual(len(release_calls), 2)

        with patch.object(check, "MAX_PAGES", 1):
            capped = check.lookup_source(
                {"type": "github_release", "repository": "example/project"}, fetch=release_fetch)
        self.assertEqual(capped["status"], "partial")

    def test_pagination_link_cannot_change_host_or_endpoint(self):
        with self.assertRaises(check.LookupFailure):
            check._safe_next_page(
                "https://hub.docker.com/v2/repositories/library/example/tags",
                "https://example.net/collect",
                "hub.docker.com",
            )
        with self.assertRaises(check.LookupFailure):
            check._safe_next_page(
                "https://ghcr.io/v2/example/app/tags/list",
                "/token",
                "ghcr.io",
            )

    def test_ghcr_image_fixture_handles_anonymous_token_challenge(self):
        calls = []

        def fetch(url, headers=None):
            calls.append((url, headers or {}))
            if url.startswith("https://ghcr.io/v2/") and not (headers or {}).get("Authorization"):
                raise check.RegistryAuthRequired(
                    'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:example/app:pull"')
            if url.startswith("https://ghcr.io/token?"):
                return {"token": "fixture-token"}
            if url.startswith("https://ghcr.io/v2/"):
                if "last=v1.0.0" in url:
                    return {"tags": ["v1.1.0"]}
                next_link = '<https://ghcr.io/v2/example/app/tags/list?n=100&last=v1.0.0>; rel="next"'
                return {"tags": ["v1.0.0", "v2.0.0-rc.1"]}, {"Link": next_link}
            raise AssertionError("unexpected fixture URL: " + url)

        result = check.lookup_source({"type": "ghcr_image", "repository": "example/app",
                                     "tag_regex": r"v?\d+\.\d+\.\d+(?:-rc\.\d+)?"}, True, fetch=fetch)

        self.assertEqual(result["candidate"], "v1.1.0")
        self.assertEqual(result["prerelease"], "v2.0.0-rc.1")
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[-1][1]["Authorization"], "Bearer fixture-token")

    def test_check_prints_recorded_compatibility_evidence(self):
        fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "dependency-report"
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            status = check.command_check(
                fixture_root,
                fixture_root / "config" / "dependencies.yaml",
                False,
                fixture_root / "responses.json",
            )

        self.assertEqual(status, 1)  # The fixture intentionally includes a failed lookup.
        self.assertIn("COMPATIBILITY | EVIDENCE", output.getvalue())
        self.assertIn("unsupported | Model catalogue fixture gap.", output.getvalue())

    def test_partial_lookup_failure_and_available_unsupported_and_derived_results(self):
        parent = component("adapter", [{"kind": "npm", "path": "tool.sh", "package": "@scope/adapter"}],
                           {"type": "npm", "package": "@scope/adapter"})
        parent["compatibility"] = {"status": "unsupported", "evidence": "Known model catalogue gap"}
        child = component("bundled-cli", [{"kind": "derived", "path": "tool.sh", "parents": ["adapter"]}],
                          {"type": "derived", "parent": "adapter"})
        failed = component("failed", [{"kind": "requirement", "path": "requirements.txt", "package": "badlib"}],
                           {"type": "pypi", "package": "badlib"})
        actual = {"npm:tool.sh:@scope/adapter": "1.0.0", "requirement:requirements.txt:badlib": "==1.0"}

        def lookup(source, include_prerelease=False, ref=None):
            if source.get("package") == "badlib":
                raise check.LookupFailure("fixture connection failure")
            return {"status": "ok", "candidate": "2.0.0", "prerelease": None, "detail": None}

        results = check.perform_check(inventory([parent, child, failed]), actual, lookup=lookup)
        by_id = {item["id"]: item for item in results}

        self.assertEqual(by_id["adapter"]["result"]["candidate"], "2.0.0")
        self.assertEqual(by_id["adapter"]["compatibility"], "unsupported")
        self.assertIsNone(by_id["bundled-cli"]["result"]["candidate"])
        self.assertEqual(by_id["bundled-cli"]["result"]["parent_candidate"], "2.0.0")
        self.assertEqual(by_id["bundled-cli"]["compatibility"], "unknown")
        self.assertEqual(by_id["failed"]["result"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
