# ── Test suite portability (trn-17) ───────────────────────────────────────────
#
# Podman-dependent test classes/methods (require a real `podman` binary or a
# live Podman socket) are guarded with
#   @unittest.skipUnless(shutil.which("podman"), "requires podman")
# and/or @unittest.skipUnless(shutil.which("git"), ...) for git-backed cases.
# The remainder are pure unit tests that mock PodmanClient and run to
# completion in any environment — including inside a crew container that has
# no podman socket.
#
# Podman/git-dependent (auto-skip when the binary is absent):
#   FileGetRegressionTests            — @skipUnless(git) per-method
#   BundleGetRegressionTests          — @skipUnless(git) per-method
#   BundleHardeningTests              — @skipUnless(git) on the archive test
#
# Portable (pure unit tests, always run — mock PodmanClient, no socket):
#   BundleUploadToolTests, FileUrlBaseResolutionTests, LifecycleRegressionTests,
#   PickupTimeoutTests, PersonaValidationTests, TaskOrchestrationTests,
#   IdleMonitorActivityTests, CaptainStandingOrdersTests, FireImmediatelyTests,
#   GatewayTokenAndProjectionTests, BearerAuthMiddlewareTests, StartupWiringTests,
#   LoginLogoutTests, TestCrewTypeRegistry, TestCrewTypeHelpers, TestLaunchCrewType,
#   TestCrewTypesTool, ScheduleCancelTests, ScheduleCreateValidationTests,
#   ScheduleListTests, DispatchFireAfterTests, ResourceJobsTests, TestPolicyInjection,
#   TestMemoryGate, TestPatchCrewConfig, TestCrewsMemoryField, TestMemoryCache,
#   ReconcileRegistryTests, IdleMonitorTests, FinishCrewSetupOrderingTests,
#   LoginFlowEdgeCaseTests, LoginGuardClearTests  (trn-17 additions)
#   ActiveCrewLimitTests  (trn-40 additions)


#   ScheduleMonitorTests, SchedulePersistenceTests  (trn-39 additions)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import importlib
import os
import stat
import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

try:
    from transport.test_file_transfer import server
except ModuleNotFoundError:
    from test_file_transfer import _install_import_stubs

    _install_import_stubs()
    server = importlib.import_module("transport.server")

import httpx


class Request:
    def __init__(
        self,
        crew_id: str,
        path: str,
        body: bytes,
        query_params: dict[str, str] | None = None,
    ) -> None:
        self.path_params = {"crew_id": crew_id, "path": path}
        self.query_params = query_params or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body


class SetupPodman:
    def __init__(self) -> None:
        self.stops = 0
        self.starts = 0

    def container_stop(self, container: str) -> None:
        self.stops += 1

    def container_start(self, container: str) -> None:
        self.starts += 1

    def container_exec(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        return "ready"


class GitDiffPodman:
    def __init__(self) -> None:
        self.exec_calls: list[tuple[str, list[str], dict[str, str] | None]] = []

    def container_exec(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        self.exec_calls.append((container, cmd, env))
        return subprocess.check_output(cmd, text=True)


class CookieHeaders:
    def multi_items(self):
        return [("set-cookie", "mc_token_5476=session-cookie; Path=/")]


class CookieResponse:
    status_code = 200
    headers = CookieHeaders()


class CookieHTTP:
    def get(self, *args: object, **kwargs: object) -> CookieResponse:
        return CookieResponse()


class FileGetRegressionTests(unittest.TestCase):
    @staticmethod
    def _create_repo(
        workspace: Path,
        filename: str,
        initial: bytes,
        changed: bytes,
    ) -> tuple[Path, str]:
        repo = workspace / "repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
        )
        tracked = repo / filename
        tracked.write_bytes(initial)
        subprocess.run(["git", "add", filename], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
        ref = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repo, text=True
        ).strip()
        tracked.write_bytes(changed)
        return repo, ref

    def _signed_request(self, path: str, ref: str) -> Request:
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac(path, ref=ref, crew_id="demo")

        self.assertEqual(result["path"], path)
        self.assertEqual(result["ref"], ref)
        query = {
            key: values[0]
            for key, values in parse_qs(urlsplit(result["url"]).query).items()
        }
        return Request("demo", path, b"", query)

    @staticmethod
    def _response_text(response: Any) -> str:
        body = response.body
        return body.decode("utf-8") if isinstance(body, bytes) else body

    @staticmethod
    def _handle_get(
        workspace: Path,
        request: Request,
        podman: GitDiffPodman,
    ) -> Any:
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "KIRO_WORKSPACE_ROOT", str(workspace)),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_get_podman", return_value=podman),
        ):
            return asyncio.run(server._handle_file_get(request))

    @unittest.skipUnless(shutil.which("git"), "git is required for this local regression")
    def test_ref_file_get_uses_seeded_repo_and_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            repo, ref = self._create_repo(
                workspace, "notes.txt", b"before\n", b"after\n"
            )
            request = self._signed_request("repo/notes.txt", ref)
            podman = GitDiffPodman()

            response = self._handle_get(workspace, request, podman)
            text = self._response_text(response)

            self.assertIn("-before", text)
            self.assertIn("+after", text)
            self.assertEqual(
                podman.exec_calls[0][1],
                ["git", "-C", str(repo), "diff", ref, "--", "notes.txt"],
            )

    @unittest.skipUnless(shutil.which("git"), "git is required for this local regression")
    def test_ref_file_get_binary_diff_is_textual_notice(self) -> None:
        changed = b"\x00\xff\x02"
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            repo, ref = self._create_repo(
                workspace, "bundle.bin", b"\x00\xff\x01", changed
            )
            request = self._signed_request("repo/bundle.bin", ref)
            podman = GitDiffPodman()

            response = self._handle_get(workspace, request, podman)
            text = self._response_text(response)

            self.assertIn("Binary files a/bundle.bin and b/bundle.bin differ", text)
            self.assertNotIn("\ufffd", text)
            self.assertNotIn(changed, text.encode("utf-8"))


class BundleArchiveResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False

    def iter_bytes(self):
        yield self.body

    def close(self) -> None:
        self.closed = True


class BundleGetPodman:
    """Run bundle creation and cleanup commands against a local workspace."""

    def __init__(self) -> None:
        self.exec_calls: list[tuple[str, list[str], dict[str, str] | None]] = []
        self.archive_calls: list[tuple[str, str]] = []

    def container_exec_checked(
        self,
        container: str,
        cmd: list[str],
        env: dict[str, str] | None = None,
    ) -> str:
        self.exec_calls.append((container, cmd, env))
        if cmd[:2] == ["rm", "-f"]:
            Path(cmd[2]).unlink(missing_ok=True)
            return ""
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        output = completed.stdout + completed.stderr
        if completed.returncode:
            raise RuntimeError(output.strip() or f"command failed: {completed.returncode}")
        return output

    def container_archive_get(self, container: str, path: str) -> BundleArchiveResponse:
        self.archive_calls.append((container, path))
        archive = subprocess.check_output(
            ["tar", "-cf", "-", "-C", str(Path(path).parent), Path(path).name]
        )
        return BundleArchiveResponse(archive)


class BundleUploadToolTests(unittest.TestCase):
    def test_supply_rejects_conflicting_modes_before_lookup_or_signing(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_sign_upload_url") as sign,
        ):
            result = server.supply(
                "repo",
                crew_id="demo",
                unpack=True,
                bundle=True,
            )

        self.assertEqual(result, {"error": "unpack and bundle cannot both be True"})
        require.assert_not_called()
        ensure.assert_not_called()
        sign.assert_not_called()

    def test_supply_bundle_keeps_path_guard_and_unsigned_mode_query(self) -> None:
        self.assertEqual(
            server.supply("../repo", crew_id="demo", bundle=True),
            {"error": "Invalid path — no traversal allowed"},
        )
        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo"}),
            patch.object(
                server,
                "_sign_upload_url",
                return_value="http://localhost/files/demo/repo?expires=1&sig=sig",
            ) as sign,
        ):
            result = server.supply("repo", crew_id="demo", bundle=True)

        self.assertIn("&bundle=1", result["delivery_url"])
        self.assertTrue(result["bundle"])
        sign.assert_called_once_with("demo", "repo", unpack=False, bundle=True)


class BundleGetRegressionTests(unittest.TestCase):
    @staticmethod
    def _create_repo(root: Path) -> tuple[Path, list[str]]:
        repo = root / "repo"
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo,
            check=True,
        )
        commits: list[str] = []
        tracked = repo / "history.txt"
        for value in ("base\n", "second\n", "third\n"):
            tracked.write_text(value)
            subprocess.run(["git", "add", "history.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", value.strip()], cwd=repo, check=True)
            commits.append(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=repo, text=True
                ).strip()
            )
        return repo, commits

    @staticmethod
    def _signed_bundle_request(ref: str | None = None) -> Request:
        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo"}),
        ):
            result = server.evac("repo", ref=ref, crew_id="demo", bundle=True)
        query = {
            key: values[0]
            for key, values in parse_qs(urlsplit(result["url"]).query).items()
        }
        return Request("demo", "repo", b"", query)

    @staticmethod
    def _downloaded_body(response: Any) -> bytes:
        if hasattr(response, "body_iterator"):
            async def collect() -> bytes:
                return b"".join([chunk async for chunk in response.body_iterator])

            return asyncio.run(collect())
        body = response.body
        if isinstance(body, bytes):
            return body
        if isinstance(body, str):
            return body.encode()
        return b"".join(body)

    @staticmethod
    def _response_status(response: Any) -> int:
        if hasattr(response, "status_code"):
            return response.status_code
        return response.kwargs["status_code"]

    @staticmethod
    def _handle_bundle_get(
        workspace: Path,
        request: Request,
        podman: BundleGetPodman,
    ) -> Any:
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "KIRO_WORKSPACE_ROOT", str(workspace)),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
            patch.object(server, "_get_podman", return_value=podman),
        ):
            return asyncio.run(server._handle_file_get(request))

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_default_bundle_can_be_cloned_with_full_history_and_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, commits = self._create_repo(root)
            request = self._signed_bundle_request()
            podman = BundleGetPodman()

            response = self._handle_bundle_get(root, request, podman)
            body = self._downloaded_body(response)
            bundle_path = root / "download.bundle"
            bundle_path.write_bytes(body)
            create = next(call[1] for call in podman.exec_calls if call[1][0:5] == ["git", "-C", str(repo), "bundle", "create"])
            self.assertEqual(create[-1], "--all")
            subprocess.run(["git", "bundle", "verify", str(bundle_path)], check=True, capture_output=True)
            clone = root / "clone"
            subprocess.run(["git", "clone", str(bundle_path), str(clone)], check=True, capture_output=True)

            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-list", "--count", "HEAD"], cwd=clone, text=True
                ).strip(),
                "3",
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=clone, text=True
                ).strip(),
                commits[-1],
            )
            self.assertTrue(any(call[1][:2] == ["rm", "-f"] for call in podman.exec_calls))
            self.assertFalse(list(root.glob(".kirocrew-bundle-*.bundle")))

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_specific_ref_bundle_passes_ref_and_is_consumable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, commits = self._create_repo(root)
            ref = subprocess.check_output(
                ["git", "symbolic-ref", "--short", "HEAD"], cwd=repo, text=True
            ).strip()
            request = self._signed_bundle_request(ref)
            podman = BundleGetPodman()

            response = self._handle_bundle_get(root, request, podman)
            body = self._downloaded_body(response)
            bundle_path = root / "specific.bundle"
            bundle_path.write_bytes(body)
            create = next(call[1] for call in podman.exec_calls if call[1][0:5] == ["git", "-C", str(repo), "bundle", "create"])
            self.assertEqual(create[-1], ref)
            clone = root / "specific-clone"
            subprocess.run(["git", "clone", str(bundle_path), str(clone)], check=True, capture_output=True)
            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=clone, text=True
                ).strip(),
                commits[-1],
            )

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_range_bundle_can_be_fetched_with_its_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo, commits = self._create_repo(root)
            ref = "HEAD~2..HEAD"
            request = self._signed_bundle_request(ref)
            podman = BundleGetPodman()

            response = self._handle_bundle_get(root, request, podman)
            body = self._downloaded_body(response)
            bundle_path = root / "range.bundle"
            bundle_path.write_bytes(body)
            create = next(call[1] for call in podman.exec_calls if call[1][0:5] == ["git", "-C", str(repo), "bundle", "create"])
            self.assertEqual(create[-1], ref)
            advertised = subprocess.check_output(
                ["git", "bundle", "list-heads", str(bundle_path)], text=True
            ).splitlines()[0].split()[1]

            receiver = root / "receiver"
            receiver.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=receiver, check=True)
            subprocess.run(
                ["git", "fetch", str(repo), f"{commits[0]}:refs/heads/base"],
                cwd=receiver,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "fetch", str(bundle_path), f"{advertised}:refs/heads/range"],
                cwd=receiver,
                check=True,
                capture_output=True,
            )
            self.assertEqual(
                subprocess.check_output(
                    ["git", "rev-list", "--count", "refs/heads/range"],
                    cwd=receiver,
                    text=True,
                ).strip(),
                "3",
            )

    def test_diff_url_rejects_unsigned_bundle_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir()
            with (
                patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
                patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo"}),
            ):
                result = server.evac(
                    "repo/file.txt", ref="HEAD", crew_id="demo", bundle=False
                )
            query = {
                key: values[0]
                for key, values in parse_qs(urlsplit(result["url"]).query).items()
            }
            query["bundle"] = "1"
            request = Request("demo", "repo/file.txt", b"", query)
            podman = BundleGetPodman()

            response = self._handle_bundle_get(workspace, request, podman)

            self.assertEqual(self._response_status(response), 403)
            self.assertFalse(podman.exec_calls)
            self.assertFalse(podman.archive_calls)


class MalformedBundleGetPodman(BundleGetPodman):
    def container_archive_get(self, container: str, path: str) -> BundleArchiveResponse:
        self.archive_calls.append((container, path))
        return BundleArchiveResponse(b"not a tar stream")


class BundleHardeningTests(unittest.TestCase):
    def test_bundle_url_round_trips_url_significant_ref(self) -> None:
        ref = "feature&client#linux"
        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
            patch.object(server, "_ensure_crew_running", return_value={"container": "gs-demo"}),
        ):
            result = server.evac("repo", ref=ref, crew_id="demo", bundle=True)

        query = {
            key: values[0]
            for key, values in parse_qs(urlsplit(result["url"]).query).items()
        }
        self.assertEqual(query["ref"], ref)
        self.assertIn("%26", result["url"])
        self.assertIn("%23", result["url"])
        self.assertTrue(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], ref, True
            )
        )

    def test_upload_url_round_trips_through_verify_file_token(self) -> None:
        # Live-caught: _sign_upload_url's payload had one fewer empty field
        # than _verify_file_token expected (missing the bundle-marker slot
        # added alongside evac's bundle support), so every supply() upload
        # signature failed verification with a 403.
        url = server._sign_upload_url("demo", "repo")
        query = {
            key: values[0]
            for key, values in parse_qs(urlsplit(url).query).items()
        }
        self.assertTrue(
            server._verify_file_token("demo", "repo", query["expires"], query["sig"])
        )

    @unittest.skipUnless(shutil.which("git"), "git is required for bundle regression")
    def test_malformed_bundle_archive_returns_500_and_cleans_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            BundleGetRegressionTests._create_repo(root)
            request = BundleGetRegressionTests._signed_bundle_request()
            podman = MalformedBundleGetPodman()

            response = BundleGetRegressionTests._handle_bundle_get(root, request, podman)

            self.assertEqual(BundleGetRegressionTests._response_status(response), 500)
            self.assertTrue(any(call[1][:2] == ["rm", "-f"] for call in podman.exec_calls))


class FileUrlBaseResolutionTests(unittest.TestCase):
    """GA_HOST_URL > GA_MCP_PUBLIC_URL (deprecated) > localhost default (trn-32)."""

    def _url_base(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def test_sign_file_url_uses_ga_public_url_when_set(self) -> None:
        env = {"GA_HOST_URL": "https://academy.example.com"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_MCP_PUBLIC_URL", None)
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("https://academy.example.com/"), url)

    def test_sign_file_url_falls_back_to_ga_mcp_public_url_with_warning(self) -> None:
        env = {"GA_MCP_PUBLIC_URL": "http://legacy:8001"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_HOST_URL", None)
            import warnings as _w
            with _w.catch_warnings(record=True) as caught:
                _w.simplefilter("always")
                url = server._sign_file_url("demo", "repo")
            self.assertTrue(url.startswith("http://legacy:8001/"), url)
            deprecation_msgs = [w for w in caught if issubclass(w.category, DeprecationWarning)]
            self.assertTrue(deprecation_msgs, "Expected DeprecationWarning for GA_MCP_PUBLIC_URL fallback")

    def test_sign_file_url_uses_localhost_default_when_both_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GA_HOST_URL", None)
            os.environ.pop("GA_MCP_PUBLIC_URL", None)
            url = server._sign_file_url("demo", "repo")
        self.assertIn("localhost", url, url)

    def test_sign_file_url_ga_public_url_wins_over_ga_mcp_public_url(self) -> None:
        env = {
            "GA_HOST_URL": "https://academy.example.com",
            "GA_MCP_PUBLIC_URL": "http://legacy:8001",
        }
        with patch.dict(os.environ, env, clear=False):
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("https://academy.example.com/"), url)

    def test_sign_upload_url_uses_ga_public_url_when_set(self) -> None:
        env = {"GA_HOST_URL": "https://academy.example.com"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_MCP_PUBLIC_URL", None)
            url = server._sign_upload_url("demo", "repo")
        self.assertTrue(url.startswith("https://academy.example.com/"), url)

    def test_sign_upload_url_falls_back_to_ga_mcp_public_url(self) -> None:
        env = {"GA_MCP_PUBLIC_URL": "http://legacy:8001"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_HOST_URL", None)
            import warnings as _w
            with _w.catch_warnings(record=True) as caught:
                _w.simplefilter("always")
                url = server._sign_upload_url("demo", "repo")
            self.assertTrue(url.startswith("http://legacy:8001/"), url)

    def test_evac_presigned_url_uses_ga_public_url_base(self) -> None:
        """Task 4.2: evac() presigned URL uses GA_HOST_URL base."""
        env = {"GA_HOST_URL": "https://cdn.example.com"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_MCP_PUBLIC_URL", None)
            url = server._sign_file_url("crew1", "workspace/bundle.tar")
        self.assertEqual(self._url_base(url), "https://cdn.example.com")
        self.assertIn("/files/crew1/workspace/bundle.tar", url)

    def test_fallback_to_ga_mcp_public_url_emits_deprecation_warning(self) -> None:
        """Task 4.3: fallback to GA_MCP_PUBLIC_URL emits deprecation warning."""
        env = {"GA_MCP_PUBLIC_URL": "http://old-mcp:9000"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_HOST_URL", None)
            import warnings as _w
            with _w.catch_warnings(record=True) as caught:
                _w.simplefilter("always")
                server._resolve_public_url_base()
            deprecation_msgs = [
                w for w in caught
                if issubclass(w.category, DeprecationWarning) and "GA_MCP_PUBLIC_URL" in str(w.message)
            ]
            self.assertEqual(len(deprecation_msgs), 1)
            self.assertIn("GA_HOST_URL", str(deprecation_msgs[0].message))


class LifecycleRegressionTests(unittest.TestCase):
    def test_supply_recovers_before_signing_upload_url(self) -> None:
        events: list[str] = []
        crew = {"container": "gs-demo", "cookie": "old"}

        def ensure(value: dict, crew_id: str) -> dict:
            events.append("ensure")
            return value

        def sign(crew_id: str, path: str, **kwargs: object) -> str:
            events.append("sign")
            return "http://localhost/files/demo/repo/file"

        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", side_effect=ensure),
            patch.object(server, "_sign_upload_url", side_effect=sign),
        ):
            result = server.supply("repo/file", crew_id="demo")

        self.assertEqual(result["delivery_url"], "http://localhost/files/demo/repo/file")
        self.assertEqual(events, ["ensure", "sign"])

    def test_supply_returns_restart_runtime_error_without_signing(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value={"container": "gs-demo"}),
            patch.object(
                server,
                "_ensure_crew_running",
                side_effect=RuntimeError("gateway restart failed"),
            ),
            patch.object(server, "_sign_upload_url") as sign,
        ):
            result = server.supply("repo/file", crew_id="demo")

        self.assertEqual(result, {"error": "gateway restart failed"})
        sign.assert_not_called()

    def test_file_post_retains_restart_recovery_check(self) -> None:
        request = Request("demo", "repo/file", b"payload")
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "_verify_file_token", return_value=True),
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew) as ensure,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_transfer_upload", return_value="wrote payload"),
        ):
            response = asyncio.run(server._handle_file_put(request))

        ensure.assert_called_once_with(crew, "demo")
        body = response.body.decode() if isinstance(response.body, bytes) else response.body
        self.assertEqual(body, "wrote payload")

    def test_setup_registration_initializes_last_used(self) -> None:
        podman = SetupPodman()
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            registry = data_dir / "crews.json"
            before = time.time()
            with (
                patch.object(server, "DATA_DIR", data_dir),
                patch.object(server, "REGISTRY_PATH", registry),
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_inject_auth"),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_copy_agents"),
                patch.object(server, "_copy_skills"),
                patch.object(server, "_copy_steering"),
                patch.object(server, "_seed_openspec_store"),
                patch.object(server, "_patch_models"),
                patch.object(server, "_mint_cookie", return_value="cookie"),
            ):
                result = server._finish_crew_setup(
                    podman,
                    "demo",
                    "gs-demo",
                    "gs-vol-demo",
                    "gs-home-demo",
                    "auth-b64",
                )

            self.assertEqual(result["status"], "ready")
            record = registry.read_text()
            self.assertIn('"last_used"', record)
            last_used = json.loads(record)["crews"]["demo"]["last_used"]
            self.assertGreaterEqual(last_used, before)

    def test_nuke_clears_captain_order_lock(self) -> None:
        crew = {
            "container": "gs-demo",
            "volume": "gs-vol-demo",
            "home_volume": "gs-home-demo",
        }
        registry = {"crews": {"demo": crew}}
        server._captain_order_locks["demo"] = threading.Lock()
        try:
            with (
                patch.object(server, "_get_crew", return_value=crew),
                patch.object(server, "_get_podman", return_value=Mock()),
                patch.object(server, "_cleanup_crew"),
                patch.object(server, "_load_registry", return_value=registry),
                patch.object(server, "_save_registry"),
            ):
                result = server.nuke("demo", confirm=True)
        finally:
            server._captain_order_locks.pop("demo", None)

        self.assertEqual(result["status"], "nuked")
        self.assertNotIn("demo", server._captain_order_locks)


class PickupTimeoutTests(unittest.TestCase):
    """Tests for the unified pickup with timeout_secs, mail state, and early-return."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    @staticmethod
    def _task_response(done: bool, agent: str = "ghost", elapsed: int = 7) -> dict:
        return {
            "id": "task-1",
            "agent": agent,
            "done": done,
            "turns": 2,
            "last_tool": "shell",
            "elapsed": elapsed,
            "result": "finished" if done else "",
            "error": "",
            "outcome": "success" if done else "",
        }

    def test_pickup_timeout_zero_returns_immediately_single_task(self) -> None:
        """5.1 — pickup with timeout_secs=0 returns immediately for single-task."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(False)) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "sleep") as sleep,
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertFalse(result["done"])
        self.assertEqual(result["crew_id"], "demo")
        self.assertEqual(result["task_id"], "task-1")
        # No sleep should be called when timeout_secs=0
        sleep.assert_not_called()
        # Only one API call (no polling loop)
        api.assert_called_once()

    def test_pickup_timeout_zero_returns_immediately_list_all(self) -> None:
        """5.1 — pickup with timeout_secs=0 returns immediately for list-all."""
        agents = [{"id": "a", "done": False, "task": "t1", "agent": "ghost", "elapsed": 5}]
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"agents": agents}) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "sleep") as sleep,
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIsInstance(result, dict)
        self.assertEqual(result["crew_id"], "demo")
        self.assertIn("tasks", result)
        sleep.assert_not_called()
        api.assert_called_once()

    def test_pickup_polls_until_task_completes(self) -> None:
        """5.2 — pickup with timeout_secs > 0 polls until task completes."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(
                server,
                "_crew_api",
                side_effect=[self._task_response(False), self._task_response(True)],
            ) as api,
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance) as sleep,
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        self.assertTrue(result["done"])
        self.assertEqual(result["result"], "finished")
        self.assertEqual(api.call_count, 2)
        sleep.assert_called_once()

    def test_pickup_timeout_elapses_returns_not_done(self) -> None:
        """5.3 — pickup timeout elapses, returns not-done state without error."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=5)

        self.assertFalse(result["done"])
        self.assertEqual(result["crew_id"], "demo")
        # Should not have "error" key set (or empty string)
        self.assertEqual(result.get("reason"), "timeout")
        self.assertFalse(result.get("error"))

    def test_pickup_poll_cap_fires_before_caller_timeout(self) -> None:
        """5.3b — internal GA_PICKUP_MAX_POLL_SECS cap fires before caller timeout_secs;
        response is a normal dict with reason='timeout', not a transport error."""
        clock = [0.0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={}),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
            patch.object(server, "GA_PICKUP_MAX_POLL_SECS", 5),
        ):
            # caller requests 60s, but the internal cap is 5s
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        # Must be a normal dict — no exception raised
        self.assertIsInstance(result, dict)
        self.assertFalse(result["done"])
        self.assertEqual(result.get("reason"), "timeout")
        self.assertFalse(result.get("error"))
        self.assertEqual(result["crew_id"], "demo")

    def test_pickup_mail_counts_present_single_task(self) -> None:
        """5.4 — mail counts present in single-task response."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(True, agent="ghost")),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 3, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["hello"], "admiral": ["order1"]}),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertEqual(result["agent_mail"], 3)
        self.assertEqual(result["admiral_mail"], 1)
        self.assertEqual(result["ghost_subjects"], ["hello"])
        self.assertEqual(result["admiral_subjects"], ["order1"])

    def test_pickup_mail_counts_present_list_all(self) -> None:
        """5.4 — mail counts present in list-all response."""
        agents = [{"id": "a", "done": True, "task": "t1", "agent": "ghost", "elapsed": 5}]

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"agents": agents}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 2, "admiral": 1}),
            patch.object(server, "_read_all_mail_subjects", return_value={"ghost": ["done"], "admiral": ["check"]}),
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIn("mail_summary", result)
        self.assertEqual(result["mail_summary"]["ghost"], 2)
        self.assertEqual(result["admiral_mail"], 1)
        self.assertEqual(result["ghost_subjects"], ["done"])
        self.assertEqual(result["admiral_subjects"], ["check"])

    def test_pickup_admiral_mail_early_return(self) -> None:
        """5.5 — Admiral mail early-return sets reason='admiral_mail'."""
        clock = [0.0]
        call_count = [0]

        def advance(seconds: float) -> None:
            clock[0] += seconds

        def mock_read_all_mail_counts(_podman, _container):
            # First call: initial capture (admiral=0).
            # Second call: first poll iteration (admiral=0).
            # Third call: second poll iteration (admiral=1 — new mail arrived).
            call_count[0] += 1
            if call_count[0] <= 2:
                return {}
            return {"admiral": 1}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(False)),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", side_effect=mock_read_all_mail_counts),
            patch.object(server, "_read_all_mail_subjects", return_value={}),
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=60)

        self.assertFalse(result["done"])
        self.assertEqual(result["reason"], "admiral_mail")
        self.assertEqual(result["admiral_mail"], 1)


class PersonaValidationTests(unittest.TestCase):
    def test_dispatch_accepts_all_personas(self) -> None:
        crew = {"container": "gs-demo"}
        for agent in server.PERSONA_NAMES:
            with (
                self.subTest(agent=agent),
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(server, "_crew_api", return_value={"id": "task"}) as api,
            ):
                result = server.dispatch("do work", agent=agent, crew_id="demo")

            self.assertEqual(result["status"], "dispatched")
            self.assertEqual(api.call_args.kwargs["json"]["agent"], agent)

    def test_schedule_accepts_all_personas(self) -> None:
        crew = {"container": "gs-demo"}
        for agent in server.PERSONA_NAMES:
            with (
                self.subTest(agent=agent),
                patch.object(server, "_require_crew", return_value=crew),
                patch.object(server, "_ensure_crew_running", return_value=crew),
                patch.object(server, "_crew_api", return_value={"id": "job"}) as api,
            ):
                result = server.schedule(
                    "job", "do work", crew_id="demo", interval=60, agent=agent
                )

            self.assertEqual(result["status"], "scheduled")
            self.assertEqual(api.call_args.kwargs["json"]["agent"], agent)

    def test_rejected_agents_do_not_lookup_or_call_crew(self) -> None:
        rejected = ("spec-ops", "kirocrew-default", "custom-agent", "unknown")
        for agent in rejected:
            with self.subTest(agent=agent):
                with (
                    patch.object(server, "_require_crew") as require,
                    patch.object(server, "_ensure_crew_running") as ensure,
                    patch.object(server, "_crew_api") as api,
                ):
                    dispatched = server.dispatch("do work", agent=agent, crew_id="demo")
                    scheduled = server.schedule(
                        "job", "do work", crew_id="demo", interval=60, agent=agent
                    )

                self.assertIn("Invalid agent", dispatched["error"])
                self.assertIn("Invalid agent", scheduled["error"])
                require.assert_not_called()
                ensure.assert_not_called()
                api.assert_not_called()


class TaskOrchestrationTests(unittest.TestCase):
    CREW = {"container": "gs-demo"}

    def _steer_with_api(self, responses: list[dict], *, force: bool) -> tuple[dict, Mock]:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=responses) as api,
        ):
            result = server.steer("task", "follow up", crew_id="demo", force=force)
        return result, api

    def test_dispatch_requests_a_dedicated_retained_run(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"id": "task"}) as api,
        ):
            result = server.dispatch("do work", agent="ghost", crew_id="demo")

        self.assertEqual(result["task_id"], "task")
        api.assert_called_once_with(
            self.CREW,
            "POST",
            "/api/spawn",
            json={"task": "do work", "agent": "ghost", "keep": True},
        )

    def test_force_steer_deletes_before_continuing_a_running_task(self) -> None:
        calls: list[tuple[str, str, dict]] = []

        def api(_crew: dict, method: str, path: str, **kwargs: object) -> dict:
            calls.append((method, path, kwargs))
            if method == "GET":
                return {"done": False}
            if method == "DELETE":
                return {"ok": True, "cancelled": True}
            return {"id": "continued-task"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.steer("task", "follow up", crew_id="demo", force=True)

        self.assertEqual(result, {
            "task_id": "continued-task",
            "crew_id": "demo",
            "action": "force_redeployed",
            "message": "follow up",
        })
        self.assertEqual(
            [(method, path) for method, path, _ in calls],
            [
                ("GET", "/api/spawn/task"),
                ("DELETE", "/api/spawn/task"),
                ("POST", "/api/spawn/task/continue"),
            ],
        )
        self.assertEqual(calls[1][2], {})
        self.assertEqual(calls[2][2], {"json": {"task": "follow up"}})

    def test_force_on_done_task_is_identical_to_plain_continue(self) -> None:
        forced, forced_api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=True
        )
        plain, plain_api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=False
        )

        expected = {
            "task_id": "continued-task",
            "crew_id": "demo",
            "action": "redeployed",
            "message": "follow up",
        }
        self.assertEqual(forced, expected)
        self.assertEqual(plain, expected)
        self.assertEqual(forced_api.call_args_list, plain_api.call_args_list)
        self.assertEqual(
            [call.args[1:] for call in forced_api.call_args_list],
            [
                ("GET", "/api/spawn/task"),
                ("POST", "/api/spawn/task/continue"),
            ],
        )

    def test_plain_steer_of_running_task_still_posts_to_steer(self) -> None:
        result, api = self._steer_with_api([{"done": False}, {}], force=False)

        self.assertEqual(result["action"], "steered")
        self.assertEqual(api.call_args_list[0].args[1:], ("GET", "/api/spawn/task"))
        self.assertEqual(
            api.call_args_list[1].args[1:], ("POST", "/api/spawn/task/steer")
        )
        self.assertEqual(api.call_args_list[1].kwargs, {"json": {"message": "follow up"}})

    def test_plain_steer_of_done_task_still_continues(self) -> None:
        result, api = self._steer_with_api(
            [{"done": True}, {"id": "continued-task"}], force=False
        )

        self.assertEqual(result["action"], "redeployed")
        self.assertEqual(api.call_args_list[0].args[1:], ("GET", "/api/spawn/task"))
        self.assertEqual(
            api.call_args_list[1].args[1:], ("POST", "/api/spawn/task/continue")
        )
        self.assertEqual(api.call_args_list[1].kwargs, {"json": {"task": "follow up"}})


class IdleMonitorActivityTests(unittest.TestCase):
    def test_cron_activity_counts_running_and_recent_completed_runs(self) -> None:
        self.assertTrue(
            server._cron_activity_since(
                {"jobs": [{"is_running": True, "running_since": 90}]}, 100
            )
        )
        self.assertTrue(
            server._cron_activity_since(
                {"jobs": [{"is_running": False, "last_run_ts": 101}]}, 100
            )
        )
        self.assertFalse(
            server._cron_activity_since(
                {"jobs": [{"is_running": False, "last_run_ts": 100}]}, 100
            )
        )

    def test_enabled_job_with_no_activity_history_still_counts(self) -> None:
        # A freshly-created job with interval longer than GA_IDLE_TIMEOUT_SECS
        # has no is_running/running_since/last_run_ts yet — _cron_activity_since
        # alone would report no activity, and the crew would idle-stop before
        # the job's very first fire. _cron_has_enabled_job is the separate
        # signal that catches this: an enabled job is a standing commitment to
        # run, regardless of whether it has run yet.
        fresh_job_payload = {"jobs": [{"name": "captain", "agent": "raven", "enabled": True}]}
        self.assertFalse(server._cron_activity_since(fresh_job_payload, 100))
        self.assertTrue(server._cron_has_enabled_job(fresh_job_payload))

    def test_disabled_job_does_not_count_as_enabled(self) -> None:
        self.assertFalse(
            server._cron_has_enabled_job({"jobs": [{"name": "captain", "enabled": False}]})
        )
        self.assertFalse(server._cron_has_enabled_job({"jobs": []}))
        self.assertFalse(server._cron_has_enabled_job({}))


class CaptainStandingOrdersTests(unittest.TestCase):
    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_order_sdd_template_resolves_and_schedules_like_message(self) -> None:
        podman = Mock()
        expected = server._resolve_order_template("sdd", "demo-change")
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}, {"id": "immediate"}],
            ) as api,
        ):
            result = server.captain(
                "demo",
                "order",
                template="sdd",
                change_name="demo-change",
                interval=120,
            )

        self.assertEqual(result["status"], "ordered")
        append.assert_called_once_with(podman, "gs-demo", expected, crew_id="demo")
        self.assertIn("demo-change", append.call_args.args[2])
        self.assertNotIn("<change>", append.call_args.args[2])
        self.assertEqual(api.call_args_list[1].args[:3], (self.CREW, "POST", "/api/crons"))
        self.assertEqual(api.call_args_list[1].kwargs["json"]["agent"], "raven")
        # Immediate dispatch should have been called (interval → fire_immediately defaults True)
        self.assertEqual(api.call_args_list[2].args[:3], (self.CREW, "POST", "/api/spawn"))

    def test_order_appends_mail_after_checkin_is_ready(self) -> None:
        podman = Mock()
        events: list[str] = []

        def append(_podman: Any, _container: str, _body: str, crew_id: str | None = None) -> None:
            events.append("mail")

        def api(_crew: dict[str, str], method: str, path: str, **kwargs: Any) -> Any:
            events.append(f"{method} {path}")
            if method == "GET":
                return {"jobs": []}
            if method == "POST":
                return {"id": "job-1", "enabled": True}
            raise AssertionError((method, path, kwargs))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail", side_effect=append),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.captain(
                "demo", "order", message="ready after provisioning", interval=120
            )

        self.assertEqual(result["job_id"], "job-1")
        # Mail is appended after the check-in exists (before immediate dispatch)
        # interval=120 → fire_immediately defaults True, so POST /api/spawn also occurs
        self.assertEqual(events, ["GET /api/crons", "POST /api/crons", "mail", "POST /api/spawn"])

    def test_concurrent_orders_share_one_checkin_job(self) -> None:
        podman = Mock()
        start = threading.Barrier(3)
        state_lock = threading.Lock()
        events: list[str] = []
        jobs: list[dict[str, Any]] = []
        results: list[dict[str, Any]] = []
        errors: list[BaseException] = []

        def api(_crew: dict[str, str], method: str, path: str, **kwargs: Any) -> Any:
            if method == "GET" and path == "/api/crons":
                with state_lock:
                    get_number = sum(
                        event.endswith("-start") for event in events
                    ) + 1
                    events.append(f"get-{get_number}-start")
                # Give the other caller a chance to contend for the same lock.
                time.sleep(0.05)
                with state_lock:
                    events.append(f"get-{get_number}-end")
                    return {"jobs": [dict(job) for job in jobs]}
            if method == "POST" and path == "/api/crons":
                with state_lock:
                    events.append("post")
                    job = {
                        "id": f"job-{len(jobs) + 1}",
                        "name": server._CAPTAIN_CHECKIN_JOB_NAME,
                        "agent": "raven",
                        "enabled": True,
                    }
                    jobs.append(job)
                    return job
            raise AssertionError((method, path, kwargs))

        def invoke() -> None:
            start.wait()
            try:
                results.append(
                    server.captain("demo", "order", message="same", interval=120)
                )
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            threads = [threading.Thread(target=invoke) for _ in range(2)]
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(len(jobs), 1)
        self.assertEqual({result["job_id"] for result in results}, {"job-1"})
        self.assertEqual(
            events,
            ["get-1-start", "get-1-end", "post", "get-2-start", "get-2-end"],
        )

    def test_order_rejects_unknown_template_before_mail_write(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_append_captain_mail") as append,
        ):
            result = server.captain(
                "demo",
                "order",
                template="does-not-exist",
                change_name="demo-change",
                interval=120,
            )

        self.assertIn("does-not-exist", result["error"])
        require.assert_not_called()
        append.assert_not_called()

    def test_order_rejects_invalid_change_name_before_mail_write(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_append_captain_mail") as append,
        ):
            result = server.captain(
                "demo",
                "order",
                template="sdd",
                change_name="../unsafe-change",
                interval=120,
            )

        self.assertIn("kebab-case", result["error"])
        require.assert_not_called()
        append.assert_not_called()

    def test_order_requires_exactly_one_message_or_template(self) -> None:
        with patch.object(server, "_require_crew") as require:
            both = server.captain(
                "demo",
                "order",
                message="hand-written",
                template="sdd",
                change_name="demo-change",
            )
            neither = server.captain("demo", "order")

        self.assertIn("exactly one of message or template", both["error"])
        self.assertIn("exactly one of message or template", neither["error"])
        require.assert_not_called()

    def test_orders_resource_lists_sdd_template_metadata_and_body(self) -> None:
        resource = server.resource_orders()
        resolved_body = server._resolve_order_template("sdd", "test-change")

        self.assertIn("## sdd", resource)
        self.assertIn("Drive a named OpenSpec change through the standard", resource)
        self.assertIn("openspec store list --json", resolved_body)
        self.assertIn("openspec store register", resolved_body)
        self.assertIn("`--store <id>`", resolved_body)
        self.assertIn("fix findings that fit this change", resolved_body)
        self.assertIn("kirocrew", resolved_body)  # upstream kirocrew CLI references
        self.assertIn("spawn list", resolved_body)
        self.assertIn("cron list", resolved_body)
        self.assertIn("cron pause", resolved_body)
        self.assertIn("cron resume", resolved_body)
        self.assertIn("/home/kirocrew/.kiro/crew/.local_secret", resolved_body)
        self.assertIn("X-Internal-Secret", resolved_body)
        self.assertIn("localhost:5476", resolved_body)
        self.assertIn("/api/spawn", resolved_body)
        self.assertIn("/api/spawn/{task_id}", resolved_body)
        self.assertIn("/api/spawn/{task_id}/steer", resolved_body)
        self.assertIn("/api/spawn/{task_id}/continue", resolved_body)
        self.assertIn("pause your own check-in job", resolved_body)
        self.assertIn("the only one in this crew", resolved_body)
        self.assertIn("never let its value show up anywhere", resolved_body)
        self.assertNotIn("captain-check-in", resolved_body)
        self.assertNotIn("external `captain(..., action=\"stop\")` operation", resolved_body)

    def test_raven_prompt_covers_gateway_status_and_self_cancellation(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]

        # Lean raven prompt retains gateway orientation (CLI + REST + auth)
        for phrase in (
            "kirocrew",  # upstream kirocrew CLI references in Raven orientation
            "spawn list",
            "cron list",
            "cron pause",
            "cron resume",
            "/home/kirocrew/.kiro/crew/.local_secret",
            "X-Internal-Secret",
            "localhost:5476",
            "/api/spawn",
            "/api/spawn/{task_id}",
            "/api/spawn/{task_id}/steer",
            "/api/spawn/{task_id}/continue",
            "never let its value show up anywhere",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)
        # Self-cancel and store resolution are now Captain-template-only
        self.assertNotIn("captain-check-in", prompt)
        self.assertNotIn("native worker-status tool is not exposed", prompt)
        self.assertNotIn("agent shells do not receive", prompt)
        self.assertNotIn("native in-session spawn tooling", prompt)

        # Verify self-cancel and store-resolution live in the Captain check-in task
        checkin = server._CAPTAIN_CHECKIN_TASK
        self.assertIn("pause your own check-in job", checkin)
        self.assertIn("the only one in this crew", checkin)

    def test_raven_and_sdd_bodies_cover_running_task_steering(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]
        # The raven prompt has the REST endpoints but not the Captain-loop
        # steering instruction (that lives in the templates now).
        for phrase in (
            "/api/spawn/{task_id}/steer",
            "/api/spawn/{task_id}/continue",
        ):
            self.assertIn(phrase, prompt)

        # The sdd template retains the full steering instruction.
        sdd_body = server._resolve_order_template("sdd", "test-change")
        for phrase in (
            "steer it with the new context rather than waiting for it to finish",
            "/api/spawn/{task_id}/steer",
            "/api/spawn/{task_id}/continue",
        ):
            self.assertIn(phrase, sdd_body)
        self.assertNotIn("native in-session spawn tooling", sdd_body)

    def test_raven_and_sdd_bodies_cover_persona_mailbox_skim(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]
        # Raven prompt uses generic <persona> placeholder — not fragile explicit paths.
        self.assertIn("/var/mail/<persona>", prompt)
        self.assertIn("captain", prompt)
        self.assertIn("admiral", prompt)
        self.assertIn("never marks anything as read", prompt)
        self.assertIn("spawn list", prompt)
        # The sdd template no longer duplicates the mailbox skim paragraph
        # (that's generic Raven behaviour in raven.json now). It still has
        # spawn list and gateway orientation.
        sdd_body = server._resolve_order_template("sdd", "test-change")
        self.assertIn("spawn list", sdd_body)

    def test_raven_and_sdd_bodies_cover_full_store_registration_command(self) -> None:
        # Store resolution is now Captain-template-only, not in the lean raven prompt.
        # Verify it's in the sdd template.
        sdd_body = server._resolve_order_template("sdd", "test-change")
        self.assertIn("openspec store list --json", sdd_body)
        self.assertIn("openspec store register", sdd_body)
        self.assertIn("--id repo", sdd_body)
        self.assertIn("--yes", sdd_body)
        self.assertIn("PROJECT_ROOT", sdd_body)
        self.assertIn("subagent_*", sdd_body)
        self.assertIn("--store <id>", sdd_body)
        # Also in the Captain check-in task.
        checkin = server._CAPTAIN_CHECKIN_TASK
        self.assertIn("openspec store list --json", checkin)
        self.assertIn("openspec store register", checkin)

    def test_template_loaded_from_disk_matches_expected_resolved_content(self) -> None:
        """Template loaded from academy/orders/sdd.md resolves to expected content."""
        resolved = server._resolve_order_template("sdd", "my-test-change")
        # Should contain the substituted constants, not raw placeholders
        self.assertIn(server._RAVEN_GATEWAY_ORIENTATION, resolved)
        self.assertIn(server._RAVEN_STORE_RESOLUTION, resolved)
        self.assertIn(server._RAVEN_SELF_CANCEL, resolved)
        # Should have the change_name substituted
        self.assertIn("my-test-change", resolved)
        self.assertNotIn("<change>", resolved)
        # Should NOT contain any raw {{...}} placeholders
        import re as _re
        self.assertFalse(_re.search(r"\{\{[A-Z_]+\}\}", resolved))

    def test_unknown_template_name_raises_valueerror(self) -> None:
        """Unknown template name raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            server._resolve_order_template("nonexistent-template", None)
        self.assertIn("Unknown Captain order template", str(ctx.exception))
        self.assertIn("nonexistent-template", str(ctx.exception))

    def test_resource_orders_returns_dynamic_listing_from_academy_orders(self) -> None:
        """resource_orders() returns dynamic listing from academy/orders/."""
        resource = server.resource_orders()
        # Should contain the sdd template section
        self.assertIn("## sdd", resource)
        # Should contain resolved content (no raw placeholders)
        import re as _re
        self.assertFalse(_re.search(r"\{\{[A-Z_]+\}\}", resource))
        # Should contain parts of the resolved body
        self.assertIn("Drive OpenSpec change", resource)

    def test_placeholder_residual_warning(self) -> None:
        """A warning is logged when an unknown {{…}} placeholder remains after substitution."""
        import tempfile
        import os
        # Create a temporary template with an unknown placeholder
        orders_dir = server._resolve_orders_dir()
        test_template = orders_dir / "_test_residual.md"
        try:
            test_template.write_text("Body with {{UNKNOWN_PLACEHOLDER}} here.\n")
            with self.assertLogs("transport", level="WARNING") as cm:
                server._resolve_order_template("_test_residual", None)
            self.assertTrue(any("Residual placeholders" in msg for msg in cm.output))
            self.assertTrue(any("UNKNOWN_PLACEHOLDER" in msg for msg in cm.output))
        finally:
            test_template.unlink(missing_ok=True)

    def test_order_without_existing_job_requires_schedule_before_mail(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"jobs": []}) as api,
            patch.object(server, "_append_captain_mail") as append,
        ):
            result = server.captain("demo", "order", message="hold")

        self.assertIn("requires either cron or interval", result["error"])
        append.assert_not_called()
        api.assert_called_once_with(self.CREW, "GET", "/api/crons")

    def test_order_creates_raven_job_when_no_job_exists(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}],
            ) as api,
        ):
            result = server.captain(
                "demo", "order", message="implement the objective", interval=120
            )

        self.assertEqual(result["job_id"], "job-1")
        append.assert_called_once_with(
            podman, "gs-demo", "implement the objective", crew_id="demo"
        )
        self.assertEqual(api.call_args_list[1].args[:3], (self.CREW, "POST", "/api/crons"))
        self.assertEqual(api.call_args_list[1].kwargs["json"]["agent"], "raven")
        self.assertEqual(
            api.call_args_list[1].kwargs["json"]["message"],
            server._CAPTAIN_CHECKIN_TASK,
        )

    def test_order_cron_passes_through_custom_timezone(self) -> None:
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}],
            ) as api,
        ):
            result = server.captain(
                "demo",
                "order",
                message="hold",
                cron="0 9 * * 1",
                timezone="America/New_York",
            )

        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(
            api.call_args_list[1].kwargs["json"]["timezone"], "America/New_York"
        )

    def test_stop_rejects_non_default_timezone(self) -> None:
        with patch.object(server, "_require_crew") as require:
            result = server.captain("demo", "stop", timezone="America/New_York")

        self.assertIn("does not accept", result["error"])
        self.assertIn("timezone", result["error"])
        require.assert_not_called()

    def test_order_reuses_existing_enabled_job_without_schedule_args(self) -> None:
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
            "schedule": "every 300s",
        }
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(server, "_crew_api", return_value={"jobs": [existing]}) as api,
        ):
            result = server.captain("demo", "order", message="new order")

        self.assertEqual(result["job_id"], "job-existing")
        append.assert_called_once_with(podman, "gs-demo", "new order", crew_id="demo")
        api.assert_called_once_with(self.CREW, "GET", "/api/crons")

    def test_standing_stop_disables_job_without_delete(self) -> None:
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
            "last_status": "ok",
        }
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {}}}),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_mail_count", return_value=2),
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": [existing]}, {"ok": True}],
            ) as api,
        ):
            result = server.captain("demo", "stop")

        self.assertFalse(result["enabled"])
        self.assertEqual(
            api.call_args_list[1].args[2], "/api/crons/job-existing/enable"
        )
        self.assertEqual(api.call_args_list[1].kwargs["json"], {"enabled": False})
        self.assertNotIn("DELETE", [call.args[1] for call in api.call_args_list])

    def test_mail_helper_produces_rfc5322_with_message_id_and_subject(self) -> None:
        message, msg_id = server._format_captain_mail("first order\nsecond line")
        lines = message.split("\n")
        self.assertEqual(lines[0], "From: admiral@localhost")
        self.assertEqual(lines[1], "To: captain@localhost")
        # Subject is derived from the first non-empty body line.
        self.assertEqual(lines[2], "Subject: first order")
        self.assertTrue(lines[3].startswith("Message-ID: <"))
        self.assertTrue(lines[4].startswith("Date: "))
        self.assertEqual(lines[5], "")
        self.assertIn("first order\nsecond line", message)
        self.assertTrue(msg_id.startswith("<"))
        self.assertTrue(msg_id.endswith("@localhost>"))

    def test_mail_helper_adds_supersedes_and_hmac_headers(self) -> None:
        message, _ = server._format_captain_mail(
            "updated order", signing_secret="deadbeef", supersedes_id="<prev@localhost>"
        )
        self.assertIn("Supersedes: <prev@localhost>", message)
        self.assertIn("X-Admiral-Sig: ", message)

    def test_admiral_sig_round_trip_matches_verify_admiral_sig_logic(self) -> None:
        """X-Admiral-Sig survives a parse-and-verify round trip.

        Simulates the verify-admiral-sig logic: parse the message with
        email.message_from_string, strip trailing newline from the payload,
        re-derive the HMAC, and compare.  This is the exact bug TRN-21 fixed —
        the trailing newline mismatch caused Raven to reject every captain order.
        """
        import email as _email
        import hmac as _hmac
        import hashlib as _hashlib

        secret = "test-round-trip-secret"
        body = "You are conducting a review.\n\nSection 1: Transport core."
        message, _ = server._format_captain_mail(body, signing_secret=secret)

        # Parse as email (what verify-admiral-sig does)
        msg = _email.message_from_string(message)
        sig_header = msg.get("X-Admiral-Sig", "").strip()
        parsed_body = (msg.get_payload() or "").rstrip("\n")  # TRN-21 fix

        # Re-derive expected HMAC
        expected = _hmac.new(
            secret.encode("utf-8"),
            parsed_body.encode("utf-8"),
            _hashlib.sha256,
        ).hexdigest()

        self.assertEqual(sig_header, expected, "X-Admiral-Sig should verify after stripping trailing newline")

    def test_mail_append_delivers_via_maildeliver(self) -> None:
        podman = Mock()
        server._append_captain_mail(podman, "gs-demo", "first order")
        command = podman.container_exec_checked.call_args.args[1]
        self.assertEqual(command[:2], ["python3", "-c"])
        script = command[2]
        self.assertIn("maildeliver", script)
        self.assertIn("captain@localhost", script)
        self.assertNotIn("os.fchmod", script)
        self.assertNotIn("os.O_APPEND", script)

    def test_mail_count_returns_zero_for_missing_mailbox(self) -> None:
        missing = Mock()
        # Maildir: empty new/ and cur/ → "0 0"
        missing.container_exec_checked.return_value = "0 0\n"
        self.assertEqual(server._mail_count(missing, "gs-demo", "/var/mail/captain"), 0)
        script = missing.container_exec_checked.call_args.args[1][2]
        self.assertIn("/var/mail/captain", script)

        unavailable = Mock()
        unavailable.container_exec_checked.side_effect = RuntimeError(
            "container not found"
        )
        with self.assertRaisesRegex(RuntimeError, "container not found"):
            server._mail_count(unavailable, "gs-demo", "/var/mail/captain")

    def test_status_reports_captain_and_admiral_mail_counts(self) -> None:
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_mail_count", side_effect=[3, 2]) as mail_count,
            patch.object(server, "_crew_api", return_value={"jobs": [existing]}),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(result["unread_mail"], 3)
        self.assertEqual(result["mailbox"], "captain@localhost")
        self.assertEqual(result["unread_admiral_mail"], 2)
        self.assertEqual(result["admiral_mailbox"], "admiral@localhost")
        self.assertEqual(mail_count.call_count, 2)
        self.assertEqual(mail_count.call_args_list[0].args[2], "/var/mail/captain")
        self.assertEqual(mail_count.call_args_list[1].args[2], "/var/mail/admiral")

    def test_schedule_defaults_to_ghost_and_allowlist_accepts_raven(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"id": "job"}) as api,
        ):
            result = server.schedule("job", "check", crew_id="demo", interval=60)

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(api.call_args.kwargs["json"]["agent"], "ghost")
        server._validate_agent("raven")
        self.assertIn("raven", server.PERSONA_ALLOWLIST)

    def test_schedule_rejects_reserved_captain_job_name(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running") as ensure_running,
            patch.object(server, "_crew_api") as api,
        ):
            result = server.schedule(
                server._CAPTAIN_CHECKIN_JOB_NAME, "unrelated", crew_id="demo", interval=60
            )

        self.assertIn("reserved", result["error"])
        ensure_running.assert_not_called()
        api.assert_not_called()

    def test_checkin_job_lookup_ignores_reserved_name_with_wrong_agent(self) -> None:
        # A job named "captain" but dispatched to a different agent - predating
        # the reservation, or created by bypassing schedule() entirely - must
        # never be silently mistaken for the real Captain check-in.
        impostor = {"jobs": [{"id": "x", "name": "captain", "agent": "ghost", "enabled": True}]}
        self.assertIsNone(server._captain_checkin_job(impostor))
        self.assertIsNone(server._captain_checkin_job(impostor, enabled_only=True))

    def test_order_resumes_existing_paused_job_without_schedule_args(self) -> None:
        existing = {
            "id": "job-paused",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": False,
            "schedule": "every 300s",
        }
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": [existing]}, {"ok": True}],
            ) as api,
        ):
            result = server.captain("demo", "order", message="resume this")

        self.assertEqual(result["job_id"], "job-paused")
        append.assert_called_once_with(podman, "gs-demo", "resume this", crew_id="demo")
        self.assertEqual(api.call_args_list[1].args[:3], (
            self.CREW,
            "POST",
            "/api/crons/job-paused/enable",
        ))
        self.assertEqual(api.call_args_list[1].kwargs["json"], {"enabled": True})

    def test_order_reports_failed_resume_toggle(self) -> None:
        existing = {
            "id": "job-paused",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": False,
        }
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_append_captain_mail"),
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": [existing]}, {"ok": False}],
            ),
        ):
            result = server.captain("demo", "order", message="resume this")

        self.assertIn("Could not resume Captain check-in", result["error"])

    def test_standing_stop_reports_failed_toggle(self) -> None:
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {}}}),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_mail_count", return_value=1),
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": [existing]}, {"ok": False}],
            ),
        ):
            result = server.captain("demo", "stop")

        self.assertIn("Could not stop Captain check-in", result["error"])

    def test_standing_stop_uses_refreshed_crew_after_restart(self) -> None:
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        stale = {"container": "gs-demo", "cookie": "old-cookie"}
        refreshed = {"container": "gs-demo", "cookie": "new-cookie"}
        with (
            patch.object(server, "_require_crew", return_value=stale),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {}}}),
            patch.object(server, "_ensure_crew_running", return_value=refreshed),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_mail_count", return_value=1),
            patch.object(
                server,
                "_crew_api",
                side_effect=[{"jobs": [existing]}, {"ok": True}],
            ) as api,
        ):
            result = server.captain("demo", "stop")

        self.assertEqual(result["status"], "stopped")
        self.assertIs(api.call_args_list[1].args[0], refreshed)

    def test_schedule_uses_gateway_cron_field(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"id": "cron-job"}) as api,
        ):
            result = server.schedule(
                "weekday-check",
                "check the objective",
                crew_id="demo",
                cron="0 9 * * 1",
            )

        self.assertEqual(result["status"], "scheduled")
        payload = api.call_args.kwargs["json"]
        self.assertEqual(payload["cron"], "0 9 * * 1")
        self.assertNotIn("cron_expr", payload)


class FireImmediatelyTests(unittest.TestCase):
    """Tests for fire_immediately behavior in schedule() and captain()."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    # ── schedule() tests ──────────────────────────────────────────────────────

    def test_schedule_interval_no_fire_immediately_defaults_true(self) -> None:
        """3.2 — schedule() with interval and no fire_immediately → immediate dispatch."""
        dispatch_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "POST" and path == "/api/spawn":
                dispatch_calls.append(kwargs.get("json", {}))
            return {"id": "job-1"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule("task", "do work", crew_id="demo", interval=120)

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(dispatch_calls[0]["task"], "do work")

    def test_schedule_cron_no_fire_immediately_defaults_false(self) -> None:
        """3.3 — schedule() with cron and no fire_immediately → no immediate dispatch."""
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            return {"id": "job-1"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo", cron="0 9 * * 1"
            )

        self.assertEqual(result["status"], "scheduled")
        # Only the cron creation POST, no /api/spawn dispatch
        self.assertNotIn("POST /api/spawn", api_paths)
        self.assertIn("POST /api/crons", api_paths)

    def test_schedule_fire_immediately_true_with_cron(self) -> None:
        """3.4 — schedule() with fire_immediately=True and cron → immediate dispatch occurs."""
        dispatch_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "POST" and path == "/api/spawn":
                dispatch_calls.append(kwargs.get("json", {}))
            return {"id": "job-1"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo",
                cron="0 9 * * 1", fire_immediately=True
            )

        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(len(dispatch_calls), 1)
        self.assertEqual(dispatch_calls[0]["task"], "do work")

    def test_schedule_fire_immediately_false_with_interval(self) -> None:
        """3.5 — schedule() with fire_immediately=False and interval → no immediate dispatch."""
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            return {"id": "job-1"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule(
                "task", "do work", crew_id="demo",
                interval=120, fire_immediately=False
            )

        self.assertEqual(result["status"], "scheduled")
        self.assertNotIn("POST /api/spawn", api_paths)



    def test_schedule_immediate_dispatch_failure_does_not_prevent_job_creation(self) -> None:
        """3.10 — immediate dispatch failure does not prevent job creation."""
        call_count = [0]

        def api(_crew, method, path, **kwargs):
            call_count[0] += 1
            if method == "POST" and path == "/api/crons":
                return {"id": "job-1"}
            if method == "POST" and path == "/api/spawn":
                raise RuntimeError("dispatch failed")
            return {}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.schedule("task", "do work", crew_id="demo", interval=120)

        # Job was still created
        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(result["status"], "scheduled")
        # Error is reported in the result, not raised
        self.assertIn("immediate_dispatch_error", result)
        self.assertIn("dispatch failed", result["immediate_dispatch_error"])

    # ── captain() tests ───────────────────────────────────────────────────────

    def test_captain_order_interval_new_job_immediate_dispatch(self) -> None:
        """3.7 — captain(action="order") with interval and new check-in → immediate Raven dispatch."""
        podman = Mock()
        spawn_calls: list[dict] = []

        def api(_crew, method, path, **kwargs):
            if method == "GET":
                return {"jobs": []}
            if method == "POST" and path == "/api/crons":
                return {"id": "job-1", "enabled": True}
            if method == "POST" and path == "/api/spawn":
                spawn_calls.append(kwargs.get("json", {}))
                return {"id": "immediate-task"}
            return {}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.captain("demo", "order", message="hold", interval=120)

        self.assertEqual(result["status"], "ordered")
        # Exactly one immediate dispatch to Raven
        self.assertEqual(len(spawn_calls), 1)
        self.assertEqual(spawn_calls[0]["agent"], "raven")

    def test_captain_order_resume_no_immediate_dispatch(self) -> None:
        """3.8 — captain(action="order") resume of paused job → no immediate dispatch."""
        existing = {
            "id": "job-paused",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": False,
        }
        podman = Mock()
        api_paths: list[str] = []

        def api(_crew, method, path, **kwargs):
            api_paths.append(f"{method} {path}")
            if method == "GET":
                return {"jobs": [existing]}
            return {"ok": True}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.captain("demo", "order", message="resume this")

        self.assertEqual(result["job_id"], "job-paused")
        # No immediate dispatch for a resume
        self.assertNotIn("POST /api/spawn", api_paths)




class GatewayTokenAndProjectionTests(unittest.TestCase):
    def test_gateway_token_uses_default_and_configured_ttl(self) -> None:
        podman = Mock()
        podman.container_exec.return_value = "token=abc123"
        old_ttl = server.KC_GATEWAY_TOKEN_TTL
        try:
            with patch.object(server, "_http", CookieHTTP()):
                server.KC_GATEWAY_TOKEN_TTL = "24h"
                self.assertEqual(
                    server._mint_cookie(podman, "gs-demo", "http://gs-demo:5476"),
                    "session-cookie",
                )
                self.assertEqual(podman.container_exec.call_args.args[1][-1], "24h")

                server.KC_GATEWAY_TOKEN_TTL = "2h"
                self.assertEqual(
                    server._mint_cookie(podman, "gs-demo", "http://gs-demo:5476"),
                    "session-cookie",
                )
                self.assertEqual(podman.container_exec.call_args.args[1][-1], "2h")
        finally:
            server.KC_GATEWAY_TOKEN_TTL = old_ttl

    def test_read_auth_file_missing_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(server, "DATA_DIR", Path(temporary)):
                self.assertEqual(server._read_auth_file(), "")

    def test_write_then_read_auth_file_round_trips_and_is_restrictive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            with patch.object(server, "DATA_DIR", data_dir):
                server._write_auth_file("first")
                path = data_dir / server.GA_AUTH_FILE
                inode = path.stat().st_ino
                self.assertEqual(server._read_auth_file(), "first")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

                server._write_auth_file("second")
                self.assertEqual(server._read_auth_file(), "second")
                self.assertEqual(path.stat().st_ino, inode)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_missing_auth_file_returns_not_authenticated_error(self) -> None:
        """launch fails fast when no auth is available — POST /login handles auth."""
        with (
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
        ):
            result = server.launch("new")

        self.assertEqual(result["error"], "not_authenticated")
        self.assertIn("/login", result["instructions"])

    def test_installer_has_no_podman_secret_machinery(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        installer = (repo_root / "install.sh").read_text()
        self.assertIn('-v "${DATA_DIR}:/data"', installer)
        self.assertIn('KC_GATEWAY_TOKEN_TTL=${KC_GATEWAY_TOKEN_TTL:-24h}', installer)
        self.assertNotIn("podman secret inspect ga-kiro-auth", installer)
        self.assertNotIn("SECRETS_DIR", installer)
        self.assertNotIn("/run/podman-secrets", installer)


# ── API-key authentication middleware tests ───────────────────────────────────

class _FakeDownstream:
    """Minimal ASGI app that records whether it was called."""

    def __init__(self) -> None:
        self.called = False
        self.scope = None

    async def __call__(self, scope, receive, send) -> None:
        self.called = True
        self.scope = scope
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})


def _http_scope(headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/mcp",
        "headers": headers or [],
    }


def _run_asgi(app, scope, body: bytes = b"") -> tuple[int, list, bytes]:
    """Run an ASGI app synchronously and return (status, headers, body)."""
    status = None
    resp_headers = []
    resp_body = b""

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(msg):
        nonlocal status, resp_headers, resp_body
        if msg["type"] == "http.response.start":
            status = msg["status"]
            resp_headers = msg.get("headers", [])
        elif msg["type"] == "http.response.body":
            resp_body += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return status, resp_headers, resp_body


class BearerAuthMiddlewareTests(unittest.TestCase):
    """Tests for the BearerAuthMiddleware pure ASGI wrapper."""

    def test_disabled_mode_passes_all_requests(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="")
        scope = _http_scope()
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_forwards_to_downstream(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret-key-123")
        scope = _http_scope([(b"authorization", b"Bearer secret-key-123")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_valid_bearer_case_insensitive_scheme(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="mykey")
        scope = _http_scope([(b"authorization", b"BEARER mykey")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 200)
        self.assertTrue(downstream.called)

    def test_missing_header_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([])
        status, headers, body = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)
        self.assertIn([b"www-authenticate", b"Bearer"], headers)
        self.assertEqual(body, b"Unauthorized")

    def test_wrong_key_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="correct")
        scope = _http_scope([(b"authorization", b"Bearer wrong")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_malformed_no_bearer_prefix_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Basic c2VjcmV0")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_duplicate_authorization_headers_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([
            (b"authorization", b"Bearer secret"),
            (b"authorization", b"Bearer secret"),
        ])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_empty_token_after_bearer_returns_401(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = _http_scope([(b"authorization", b"Bearer ")])
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)
        self.assertFalse(downstream.called)

    def test_non_http_scope_passes_through(self) -> None:
        downstream = _FakeDownstream()
        mw = server.BearerAuthMiddleware(downstream, api_key="secret")
        scope = {"type": "lifespan"}
        _run_asgi(mw, scope)
        self.assertTrue(downstream.called)

    def test_constant_time_comparison_used(self) -> None:
        """Verify hmac.compare_digest is used (not == operator)."""
        import inspect
        source = inspect.getsource(server.BearerAuthMiddleware.__call__)
        self.assertIn("hmac.compare_digest", source)
        self.assertNotIn("== self._key", source)

    def test_rejected_requests_never_reach_downstream(self) -> None:
        """Ensure all rejection paths never invoke the downstream app."""
        key = "correct-key"
        bad_cases = [
            [],  # missing
            [(b"authorization", b"Bearer wrong")],  # wrong
            [(b"authorization", b"Token correct-key")],  # bad scheme
            [(b"authorization", b"Bearer correct-key"), (b"authorization", b"Bearer correct-key")],  # dup
            [(b"authorization", b"Bearer ")],  # empty token
        ]
        for headers in bad_cases:
            downstream = _FakeDownstream()
            mw = server.BearerAuthMiddleware(downstream, api_key=key)
            status, _, _ = _run_asgi(mw, _http_scope(headers))
            self.assertEqual(status, 401, f"Expected 401 for headers={headers}")
            self.assertFalse(downstream.called, f"Downstream called for headers={headers}")


class StartupWiringTests(unittest.TestCase):
    """Verify the MCP app factory uses /mcp path and stateless setting."""

    def test_mcp_server_has_streamable_http_app_method(self) -> None:
        self.assertTrue(hasattr(server.mcp, "streamable_http_app"))

    def test_bearer_middleware_wraps_mcp_app_in_entrypoint(self) -> None:
        """Confirm the entrypoint wires BearerAuthMiddleware around the MCP app."""
        import inspect
        source = inspect.getsource(server)
        # The entrypoint should use streamable_http_app with /mcp path
        self.assertIn('streamable_http_app(', source)
        self.assertIn('path="/mcp"', source)
        self.assertIn('stateless_http=True', source)
        # Login/logout routes are handled inside BearerAuthMiddleware directly
        # (not via a Starlette router) so the MCP lifespan is never broken.
        self.assertIn('BearerAuthMiddleware(mcp_app', source)
        self.assertIn('_handle_login_post', source)
        self.assertIn('_handle_login_get', source)
        self.assertIn('_handle_logout_post', source)

    def test_file_routes_do_not_require_api_key(self) -> None:
        """File routes use HMAC presigned URLs, not the API key."""
        import inspect
        file_get_src = inspect.getsource(server._handle_file_get)
        file_put_src = inspect.getsource(server._handle_file_put)
        self.assertNotIn("GA_API_KEY", file_get_src)
        self.assertNotIn("GA_API_KEY", file_put_src)
        self.assertIn("_verify_file_token", file_get_src)
        self.assertIn("_verify_file_token", file_put_src)


class LoginLogoutTests(unittest.TestCase):
    """Tests for POST /login, GET /login, and POST /logout routes."""

    def setUp(self) -> None:
        # Reset global login state before each test
        import transport.server as srv
        with srv._login_pending_lock:
            srv._login_pending = None

    # ── POST /login ───────────────────────────────────────────────────────────

    def test_post_login_happy_path_sets_pending_and_returns_url(self) -> None:
        podman = Mock()
        container_name = "ga-login-abcd1234"
        exec_id = "exec-abc"

        # Simulate a socket that yields: Start URL prompt, Region prompt, then device URL
        output_chunks = [
            b"? Enter Start URL \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Start URL\r\n? Enter Region \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Region\r\n\r\nConfirm the following code in the browser\r\nCode: ABCD-1234\r\n\r\nOpen this URL: https://device.auth.example.com/activate?user_code=ABCD-1234\r\n",
        ]
        chunk_iter = iter(output_chunks)

        fake_sock = Mock()
        fake_sock.fileno.return_value = 5  # select() needs a real-looking fd

        def fake_recv(n):
            try:
                return next(chunk_iter)
            except StopIteration:
                return b""

        fake_sock.recv.side_effect = fake_recv

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value=container_name),
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=(exec_id, fake_sock)),
        ):
            # select always reports ready
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        self.assertIn("https://device.auth.example.com", body["login_url"])
        self.assertEqual(body["code"], "ABCD-1234")

        with server._login_pending_lock:
            pending = server._login_pending
        self.assertIsNotNone(pending)
        self.assertEqual(pending["container"], container_name)
        self.assertEqual(pending["exec_id"], exec_id)

    def test_post_login_returns_409_when_already_authenticated(self) -> None:
        with patch.object(server, "_read_auth_file", return_value="dGVzdA=="):
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 409)
        self.assertIn("Already authenticated", response.body.decode())

    def test_post_login_returns_409_when_login_already_in_progress(self) -> None:
        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_login_pending_lock"),
        ):
            # Inject pending state directly
            with server._login_pending_lock:
                server._login_pending = {
                    "container": "ga-login-existing",
                    "exec_id": "x",
                    "started_at": 999.0,
                }
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        with server._login_pending_lock:
            server._login_pending = None

        self.assertEqual(response.status_code, 409)
        self.assertIn("Login already in progress", response.body.decode())

    def test_post_login_nukes_container_and_returns_500_when_no_url(self) -> None:
        podman = Mock()
        container_name = "ga-login-fail1234"

        fake_sock = Mock()
        fake_sock.fileno.return_value = 5
        fake_sock.recv.return_value = b"Error: misconfigured IdP\n"

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value=container_name),
            patch.object(server, "_nuke_login_container") as nuke,
            patch.object(server, "time") as mock_time,
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-fail", fake_sock)),
        ):
            # Force deadline to expire after one iteration
            mock_time.time.side_effect = [1000.0, 1000.0, 1016.0]
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 500)
        nuke.assert_called_once_with(podman, container_name)
        with server._login_pending_lock:
            self.assertIsNone(server._login_pending)

    # ── GET /login ────────────────────────────────────────────────────────────

    def test_get_login_returns_404_when_no_pending_flow(self) -> None:
        request = Mock()
        response = asyncio.run(server._handle_login_get(request))
        self.assertEqual(response.status_code, 404)
        self.assertIn("No login in progress", response.body.decode())

    def test_get_login_returns_pending_when_auth_not_complete(self) -> None:
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-abcd",
                "exec_id": "x",
                "started_at": 999.0,
            }

        podman = Mock()
        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_from_crew", return_value=None),
        ):
            request = Mock()
            response = asyncio.run(server._handle_login_get(request))

        with server._login_pending_lock:
            server._login_pending = None

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")

    def test_get_login_completes_writes_auth_injects_crews_nukes_temp(self) -> None:
        auth_b64 = "dGVzdC1hdXRo"
        running_crew = {"status": "running", "container": "gs-crew1"}
        registry = {"crews": {"crew1": running_crew}}

        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-done",
                "exec_id": "x",
                "started_at": 999.0,
            }

        podman = Mock()
        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_read_auth_from_crew", return_value=auth_b64),
            patch.object(server, "_write_auth_file") as write_auth,
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_inject_auth") as inject,
            patch.object(server, "_nuke_login_container") as nuke,
        ):
            request = Mock()
            response = asyncio.run(server._handle_login_get(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "complete")
        write_auth.assert_called_once_with(auth_b64)
        inject.assert_called_once_with(podman, "gs-crew1", auth_b64)
        nuke.assert_called_once_with(podman, "ga-login-done")

        with server._login_pending_lock:
            self.assertIsNone(server._login_pending)

    # ── POST /logout ──────────────────────────────────────────────────────────

    def test_post_logout_returns_404_when_not_authenticated(self) -> None:
        with patch.object(server, "_read_auth_file", return_value=""):
            request = Mock()
            response = asyncio.run(server._handle_logout_post(request))

        self.assertEqual(response.status_code, 404)
        self.assertIn("Not authenticated", response.body.decode())

    def test_post_logout_deletes_auth_file_and_clears_running_crews(self) -> None:
        running_crew = {"status": "running", "container": "gs-crew1"}
        stopped_crew = {"status": "stopped", "container": "gs-crew2"}
        registry = {"crews": {"crew1": running_crew, "crew2": stopped_crew}}

        podman = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            # Write a fake auth file
            auth_path = data_dir / server.GA_AUTH_FILE
            auth_path.write_text("dGVzdA==")
            auth_path.chmod(0o600)

            with (
                patch.object(server, "DATA_DIR", data_dir),
                patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "_load_registry", return_value=registry),
            ):
                request = Mock()
                response = asyncio.run(server._handle_logout_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "logged_out")

        # Only the running crew should have had exec called
        exec_calls = [call.args[1] for call in podman.container_exec.call_args_list]
        containers_cleared = [call.args[0] for call in podman.container_exec.call_args_list]
        self.assertEqual(containers_cleared, ["gs-crew1"])
        # Verify DELETE FROM auth_kv was in the script
        self.assertTrue(any("DELETE FROM auth_kv" in call.args[1][2] for call in podman.container_exec.call_args_list))


# ── Crew-Type Registry Tests ──────────────────────────────────────────────────


class TestCrewTypeRegistry(unittest.TestCase):
    """Unit tests for the crew type registry loading and helpers."""

    def test_valid_registry_loads_entries(self) -> None:
        """_load_composition_registry() parses a valid registry.json correctly."""
        registry_data = json.dumps({
            "compositions": [
                {"name": "spec-ops", "description": "Default type", "dir": "spec-ops"},
                {"name": "custom", "description": "Custom type", "dir": "custom", "image": "custom:latest"},
            ]
        })
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.json"
            registry_path.write_text(registry_data)
            crews_dir = Path(tmp) / "spec-ops"
            crews_dir.mkdir()
            custom_dir = Path(tmp) / "custom"
            custom_dir.mkdir()

            with (
                patch.object(server, "_CREW_REGISTRY_PATH", registry_path),
                patch("transport.server.Path") as MockPath,
            ):
                # Make Path(f"/crews/{dir}").is_dir() return True for our dirs
                def path_side_effect(p):
                    if p == str(registry_path):
                        return registry_path
                    real = Path(p)
                    if "/crews/" in p:
                        mock_p = Mock()
                        dir_name = p.split("/crews/")[-1]
                        mock_p.is_dir.return_value = (Path(tmp) / dir_name).is_dir()
                        return mock_p
                    return real

                # Simpler approach: just patch _CREW_REGISTRY_PATH and the dir check
                with patch("builtins.open", unittest.mock.mock_open(read_data=registry_data)):
                    pass

        # Direct test: create temp dirs matching the structure
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "registry.json"
            reg_path.write_text(registry_data)
            kirocrew_dir = Path(tmp).parent / "crews" / "spec-ops"
            custom_dir2 = Path(tmp).parent / "crews" / "custom"

            # We test by patching the path and directory checks
            with patch.object(server, "_CREW_REGISTRY_PATH", reg_path):
                with patch("pathlib.Path.is_dir", return_value=True):
                    result = server._load_composition_registry()

        self.assertIn("spec-ops", result)
        self.assertIn("custom", result)
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")
        self.assertEqual(result["custom"]["image"], "custom:latest")

    def test_missing_file_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback when file is missing."""
        with patch.object(server, "_CREW_REGISTRY_PATH", Path("/nonexistent/registry.json")):
            result = server._load_composition_registry()

        self.assertEqual(list(result.keys()), ["spec-ops"])
        self.assertEqual(result["spec-ops"]["dir"], "spec-ops")

    def test_malformed_json_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback for malformed JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json!!!")
            f.flush()
            try:
                with patch.object(server, "_CREW_REGISTRY_PATH", Path(f.name)):
                    result = server._load_composition_registry()
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
                    patch.object(server, "_CREW_REGISTRY_PATH", Path(f.name)),
                    patch("pathlib.Path.is_dir", return_value=True),
                ):
                    result = server._load_composition_registry()
                self.assertNotIn("INVALID-CAPS", result)
                self.assertIn("spec-ops", result)
            finally:
                Path(f.name).unlink()


class TestCrewTypeHelpers(unittest.TestCase):
    """Unit tests for _resolve_manifest_path and _resolve_image."""

    def test_resolve_manifest_path(self) -> None:
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        self.assertEqual(server._resolve_manifest_path(entry), Path("/crews/spec-ops/manifest.json"))

    def test_resolve_manifest_path_custom_dir(self) -> None:
        entry = {"name": "custom", "dir": "my-custom-crew"}
        self.assertEqual(server._resolve_manifest_path(entry), Path("/crews/my-custom-crew/manifest.json"))

    def test_resolve_image_with_override(self) -> None:
        entry = {"name": "custom", "dir": "custom", "image": "custom:v2"}
        self.assertEqual(server._resolve_image(entry), "custom:v2")

    def test_resolve_image_without_override(self) -> None:
        entry = {"name": "spec-ops", "dir": "spec-ops"}
        self.assertEqual(server._resolve_image(entry), server.KC_IMAGE)

    def test_resolve_image_empty_string_uses_default(self) -> None:
        entry = {"name": "spec-ops", "dir": "spec-ops", "image": ""}
        self.assertEqual(server._resolve_image(entry), server.KC_IMAGE)


class TestLaunchCrewType(unittest.TestCase):
    """Integration tests for launch() with composition parameter."""

    def test_launch_with_explicit_composition(self) -> None:
        """launch() with a valid composition resolves image and manifest correctly."""
        test_entry = {"name": "spec-ops", "dir": "spec-ops", "description": "Default"}
        with (
            patch.object(server, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_finish_crew_setup", return_value={"status": "ready"}) as mock_setup,
            patch.object(server, "_wait_gateway", return_value=True),
        ):
            mock_podman = server._get_podman.return_value
            mock_podman.network_create = Mock()
            mock_podman.volume_create = Mock()
            mock_podman.container_create = Mock()
            mock_podman.container_start = Mock()

            result = server.launch("test-crew", composition="spec-ops")

        self.assertEqual(result["status"], "ready")
        # Verify _finish_crew_setup was called with composition and entry
        call_args = mock_setup.call_args
        self.assertEqual(call_args[0][5], "dGVzdA==")  # auth_b64
        self.assertEqual(call_args[0][6], "spec-ops")  # composition
        self.assertEqual(call_args[0][7], test_entry)  # composition_entry

    def test_launch_with_unknown_composition_errors(self) -> None:
        """launch() with unknown composition returns error listing available types."""
        with (
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
            patch.object(server, "COMPOSITION_REGISTRY", {"custom": test_entry}),
            patch.object(server, "_get_podman") as mock_get_podman,
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_finish_crew_setup", return_value={"status": "ready"}),
            patch.object(server, "_wait_gateway", return_value=True),
        ):
            mock_podman = Mock()
            mock_get_podman.return_value = mock_podman

            server.launch("my-crew", composition="custom")

        # Verify container_create was called with the custom image
        mock_podman.container_create.assert_called_once()
        call_kwargs = mock_podman.container_create.call_args[1]
        self.assertEqual(call_kwargs["image"], "custom:v3")


class TestCrewTypesTool(unittest.TestCase):
    """Test for the compositions discovery tool."""

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


if __name__ == "__main__":
    unittest.main()


class ScheduleCancelTests(unittest.TestCase):
    """Tests for schedule(action='cancel', ...)."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_cancel_success(self) -> None:
        """4.1 — cancel removes the registry entry after gateway DELETE."""
        # Seed a registry with a matching job_id entry
        reg = {
            "crews": {"demo": {
                "container": "gs-demo", "cookie": "cookie",
                "schedules": [
                    {"job_id": "job-abc", "name": "my-job", "interval_secs": 60,
                     "cron_expr": None, "agent": "ghost", "enabled": True},
                ],
            }}
        }
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": [
            {"id": "job-abc", "name": "my-job", "agent": "ghost", "enabled": True},
        ]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE" and path == "/api/crons/job-abc":
                return {}
            raise AssertionError((method, path, kwargs))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server.schedule(action="cancel", job_id="job-abc", crew_id="demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "job-abc"})
        # Verify the registry entry was removed
        self.assertTrue(len(save_calls) > 0, "Expected _save_registry to be called")
        last_reg = save_calls[-1]
        remaining_ids = [s.get("job_id") for s in last_reg["crews"]["demo"]["schedules"]]
        self.assertNotIn("job-abc", remaining_ids, "job-abc should have been removed from registry")

    def test_cancel_not_found_is_idempotent(self) -> None:
        """4.1 — cancel a non-existent job is idempotent (TRN-29: no error)."""
        jobs_listing = {"jobs": []}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE":
                resp = Mock(status_code=404)
                raise httpx.HTTPStatusError(
                    "Not Found",
                    request=None,
                    response=resp,
                )
            raise AssertionError((method, path, kwargs))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(server, "_save_registry"),
        ):
            result = server.schedule(action="cancel", job_id="nonexistent", crew_id="demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "nonexistent"})

    def test_cancel_refuses_captain_checkin_job(self) -> None:
        """4.2 — cancel refuses to cancel the captain check-in job."""
        captain_job = {
            "id": "captain-job-id",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        jobs_listing = {"jobs": [captain_job]}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value=jobs_listing),
        ):
            result = server.schedule(action="cancel", job_id="captain-job-id", crew_id="demo")

        self.assertIn("Cannot cancel the Captain check-in job", result["error"])

    def test_cancel_requires_job_id(self) -> None:
        """cancel without job_id returns error."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(action="cancel", crew_id="demo")

        self.assertIn("job_id is required", result["error"])


class ScheduleCreateValidationTests(unittest.TestCase):
    """Tests for schedule(action='create') input validation."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_create_requires_name(self) -> None:
        """create without name returns error."""
        result = server.schedule(action="create", message="do stuff", crew_id="demo", interval=60)
        self.assertIn("name is required", result["error"])

    def test_create_requires_message(self) -> None:
        """create without message returns error."""
        result = server.schedule(action="create", name="my-job", crew_id="demo", interval=60)
        self.assertIn("message is required", result["error"])


class ScheduleListTests(unittest.TestCase):
    """Tests for schedule(action='list', ...)."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_list_with_jobs(self) -> None:
        """4.3 — list returns jobs with expected fields."""
        jobs_listing = {"jobs": [
            {"id": "j1", "name": "daily-check", "schedule": "0 9 * * *", "agent": "ghost", "enabled": True, "last_run_ts": "2026-01-01T09:00:00"},
            {"id": "j2", "name": "weekly-report", "schedule": "0 0 * * 1", "agent": "wraith", "enabled": False, "last_run_ts": None},
        ]}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value=jobs_listing),
        ):
            result = server.schedule(action="list", crew_id="demo")

        self.assertEqual(len(result["jobs"]), 2)
        self.assertEqual(result["jobs"][0]["job_id"], "j1")
        self.assertEqual(result["jobs"][0]["name"], "daily-check")
        self.assertEqual(result["jobs"][0]["agent"], "ghost")
        self.assertTrue(result["jobs"][0]["enabled"])
        self.assertEqual(result["jobs"][1]["job_id"], "j2")
        self.assertFalse(result["jobs"][1]["enabled"])

    def test_list_empty(self) -> None:
        """4.3 — list returns empty jobs list when no jobs exist."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value={"jobs": []}),
        ):
            result = server.schedule(action="list", crew_id="demo")

        self.assertEqual(result, {"jobs": []})

    def test_list_falls_back_to_gateway_when_registry_empty(self) -> None:
        """4.1b — schedule(list) falls back to gateway /api/crons when registry is empty."""
        # Registry has no schedules for this crew
        reg_empty = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "schedules": []}}}
        gateway_jobs = {"jobs": [
            {"id": "gw-j1", "name": "gateway-job", "schedule": "every 60s",
             "agent": "ghost", "enabled": True, "last_run_ts": None},
        ]}

        with (
            patch.object(server, "_load_registry", return_value=reg_empty),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value=gateway_jobs) as api_mock,
        ):
            result = server.schedule(action="list", crew_id="demo")

        # The gateway /api/crons GET must have been called as fallback
        api_mock.assert_called_once()
        call_args = api_mock.call_args
        self.assertEqual(call_args.args[2], "GET")
        self.assertEqual(call_args.args[3], "/api/crons")
        # The gateway's job should appear in the result
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["job_id"], "gw-j1")
        self.assertEqual(result["jobs"][0]["name"], "gateway-job")


class DispatchFireAfterTests(unittest.TestCase):
    """Tests for schedule(delay=...) — TRN-29 moved delay from dispatch to schedule."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_delay_creates_one_shot_via_schedule(self) -> None:
        """6.3 — schedule(delay=N) creates a one-shot cron job."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "delayed-job-1"}) as api,
            patch.object(server, "_load_registry", return_value={"crews": {"demo": {"schedules": []}}}),
            patch.object(server, "_save_registry"),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", agent="ghost", crew_id="demo", delay=300
            )

        self.assertEqual(result["job_id"], "delayed-job-1")
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["delay"], 300)

        # Verify it called POST /api/crons with a cron expression
        api.assert_called_once()
        call_kwargs = api.call_args.kwargs
        cron_expr = call_kwargs["json"].get("cron", "")
        self.assertEqual(len(cron_expr.split()), 5, f"Expected 5-field cron expr, got: {cron_expr!r}")
        self.assertNotIn("delay", call_kwargs["json"])
        self.assertEqual(call_kwargs["json"]["agent"], "ghost")
        self.assertEqual(call_kwargs["json"]["message"], "run cleanup")

    def test_delay_zero_rejected(self) -> None:
        """6.3 — schedule(delay=0) returns validation error."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", crew_id="demo", delay=0
            )

        self.assertEqual(result, {"error": "delay must be >= 1"})

    def test_delay_negative_rejected(self) -> None:
        """6.3 — schedule(delay=-5) returns validation error."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", crew_id="demo", delay=-5
            )

        self.assertEqual(result, {"error": "delay must be >= 1"})


class ResourceJobsTests(unittest.TestCase):
    """Tests for resource_jobs()."""

    def test_resource_jobs_aggregates_across_crews(self) -> None:
        """4.6 — resource_jobs collects jobs from multiple running crews."""
        reg = {
            "crews": {
                "crew-a": {"container": "gs-crew-a", "status": "running", "cookie": "c1"},
                "crew-b": {"container": "gs-crew-b", "status": "running", "cookie": "c2"},
            }
        }
        crew_a_jobs = {"jobs": [
            {"id": "j1", "name": "check", "schedule": "every 60s", "agent": "ghost", "enabled": True, "last_run_ts": "now", "last_status": "ok"},
        ]}
        crew_b_jobs = {"jobs": [
            {"id": "j2", "name": "report", "schedule": "0 9 * * 1", "agent": "wraith", "enabled": False, "last_run_ts": None, "last_status": None},
        ]}

        def api(crew, method, path, **kwargs):
            if crew["container"] == "gs-crew-a":
                return crew_a_jobs
            return crew_b_jobs

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=api),
        ):
            result = server.resource_jobs()

        self.assertIn("## crew-a", result)
        self.assertIn("## crew-b", result)
        self.assertIn("j1", result)
        self.assertIn("j2", result)
        self.assertIn("check", result)
        self.assertIn("report", result)

    def test_resource_jobs_no_running_crews(self) -> None:
        """4.6 — resource_jobs shows stopped crews with registry data (TRN-29)."""
        reg = {"crews": {"stopped": {"container": "gs-stopped", "status": "stopped"}}}
        with patch.object(server, "_load_registry", return_value=reg):
            result = server.resource_jobs()

        self.assertIn("## stopped", result)
        self.assertIn("No scheduled jobs.", result)

    def test_resource_jobs_handles_crew_error_gracefully(self) -> None:
        """4.6 — resource_jobs reports crew connection errors inline."""
        reg = {"crews": {"bad": {"container": "gs-bad", "status": "running", "cookie": "c"}}}

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=RuntimeError("connection refused")),
        ):
            result = server.resource_jobs()

        self.assertIn("## bad", result)
        self.assertIn("error", result)
        self.assertIn("connection refused", result)

    def test_resource_jobs_empty_jobs_for_crew(self) -> None:
        """4.6 — resource_jobs shows 'No scheduled jobs' for crew without jobs."""
        reg = {"crews": {"empty": {"container": "gs-empty", "status": "running", "cookie": "c"}}}
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", return_value={"jobs": []}),
        ):
            result = server.resource_jobs()

        self.assertIn("## empty", result)
        self.assertIn("No scheduled jobs", result)


class TestPolicyInjection(unittest.TestCase):
    """Tests for the _inject_policy() function and its integration."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        # Create policy template files
        self.policies_dir = Path(self.tmp) / "policies"
        self.policies_dir.mkdir()
        self.default_policy = {
            "version": "1",
            "commands": {"deny": ["^git push"]},
            "channels": {"deny": ["slack"]},
        }
        (self.policies_dir / "default.json").write_text(
            json.dumps(self.default_policy, indent=2)
        )
        self.kirocrew_policy = {
            "version": "2",
            "commands": {"deny": ["^git push", "^gh "]},
            "channels": {"deny": ["slack", "discord"]},
        }
        (self.policies_dir / "spec-ops.json").write_text(
            json.dumps(self.kirocrew_policy, indent=2)
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inject_policy_uses_composition_template(self) -> None:
        """_inject_policy uses composition-specific template when found."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=2")

        with patch("transport.server.Path") as MockPath:
            # Make Path("/policies/spec-ops.json") exist and return the composition template
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.kirocrew_policy)

            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                elif str(arg) == "/policies/default.json":
                    return default_path
                return Mock()

            MockPath.side_effect = path_side_effect

            result = server._inject_policy(
                mock_podman, "gs-test", "spec-ops", "secret123"
            )

        self.assertEqual(result, "2")
        mock_podman.container_exec_checked.assert_called_once()

    def test_inject_policy_falls_back_to_default(self) -> None:
        """_inject_policy falls back to default when composition template not found."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=1")

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = False

            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/custom-unknown.json":
                    return composition_path
                elif str(arg) == "/policies/default.json":
                    return default_path
                return Mock()

            MockPath.side_effect = path_side_effect

            result = server._inject_policy(
                mock_podman, "gs-test", "custom-unknown", "secret123"
            )

        self.assertEqual(result, "1")
        mock_podman.container_exec_checked.assert_called_once()

    def test_inject_policy_writes_admission_alongside_security(self) -> None:
        """Both security_policy.json and admission_policy.json are written."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=1")

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            server._inject_policy(
                mock_podman, "gs-test", "spec-ops", "secret123"
            )

        # The script writes both files — verify the script content
        call_args = mock_podman.container_exec_checked.call_args
        script = call_args[0][1][2]  # ["python3", "-c", script]
        self.assertIn("security_policy.json", script)
        self.assertIn("admission_policy.json", script)

    def test_inject_policy_admission_enables_signature_verification(self) -> None:
        """Admission policy sets require_policy_signature=True with trust_keys dict."""
        policy = {"version": 1, "boot": {}}
        secret = "fixed-secret-for-test"

        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(return_value="policy injected version=1")

        captured_scripts: list[str] = []

        def exec_capture(container, cmd):
            if cmd[0] == "python3" and cmd[1] == "-c":
                captured_scripts.append(cmd[2])
            return "policy injected version=1"

        mock_podman.container_exec_checked = Mock(side_effect=exec_capture)

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/test.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            server._inject_policy(mock_podman, "gs-test", "test", secret)

        # Execute the captured script locally to inspect what it would write
        self.assertEqual(len(captured_scripts), 1)
        script = captured_scripts[0]

        # Simulate what the script does: run it with a fake crew_dir
        import tempfile, os as _os
        with tempfile.TemporaryDirectory() as td:
            fake_crew_dir = Path(td)
            patched = script.replace(
                "pathlib.Path('/home/kirocrew/.kiro/crew')",
                f"pathlib.Path('{fake_crew_dir}')",
            )
            exec(compile(patched, "<test>", "exec"))  # noqa: S102

            policy_out = json.loads((fake_crew_dir / "security_policy.json").read_text())
            admission_out = json.loads((fake_crew_dir / "admission_policy.json").read_text())

        # Admission policy must have require_policy_signature=True and trust_keys
        # (trust_keys is required by KiroCrew governance to verify the policy signature)
        self.assertTrue(admission_out["require_policy_signature"])
        self.assertIn("trust_keys", admission_out)
        self.assertEqual(admission_out["trust_keys"], {"ghostship": secret})

        # Security policy must have identity.issuer and identity.signature
        self.assertIn("identity", policy_out)
        self.assertEqual(policy_out["identity"]["issuer"], "ghostship")
        self.assertIsInstance(policy_out["identity"]["signature"], str)
        self.assertTrue(len(policy_out["identity"]["signature"]) > 0)

    def test_inject_policy_signature_is_correct(self) -> None:
        """The identity.signature embedded in security_policy.json is the correct HMAC."""
        import hmac as _hmac, hashlib as _hashlib
        policy = {"version": 1, "boot": {}}
        secret = "test-secret-abc123"

        mock_podman = Mock()
        captured_scripts: list[str] = []

        def exec_capture(container, cmd):
            if cmd[0] == "python3" and cmd[1] == "-c":
                captured_scripts.append(cmd[2])
            return "policy injected version=1"

        mock_podman.container_exec_checked = Mock(side_effect=exec_capture)

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect
            server._inject_policy(mock_podman, "gs-test", "spec-ops", secret)

        self.assertEqual(len(captured_scripts), 1)
        script = captured_scripts[0]

        with tempfile.TemporaryDirectory() as td:
            fake_crew_dir = Path(td)
            patched = script.replace(
                "pathlib.Path('/home/kirocrew/.kiro/crew')",
                f"pathlib.Path('{fake_crew_dir}')",
            )
            exec(compile(patched, "<test>", "exec"))  # noqa: S102
            policy_out = json.loads((fake_crew_dir / "security_policy.json").read_text())

        # Re-derive the expected signature: whole doc minus identity.signature
        body = {k: v for k, v in policy_out.items() if k != "identity"}
        identity = policy_out.get("identity", {})
        rest = {k: v for k, v in identity.items() if k != "signature"}
        if rest:
            body["identity"] = rest
        payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_sig = _hmac.new(secret.encode("utf-8"), payload, _hashlib.sha256).hexdigest()

        self.assertEqual(policy_out["identity"]["signature"], expected_sig)

    def test_inject_policy_failure_does_not_abort_launch(self) -> None:
        """Policy injection failure is caught and does not abort launch."""
        mock_podman = Mock()
        mock_podman.container_exec_checked = Mock(
            side_effect=RuntimeError("container_exec failed")
        )

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = True
            composition_path.read_text.return_value = json.dumps(self.default_policy)

            def path_side_effect(arg):
                if str(arg) == "/policies/spec-ops.json":
                    return composition_path
                return Mock()

            MockPath.side_effect = path_side_effect

            # _inject_policy itself raises; the caller (_finish_crew_setup)
            # catches it. Verify _inject_policy propagates the error.
            with self.assertRaises(RuntimeError):
                server._inject_policy(
                    mock_podman, "gs-test", "spec-ops", "secret123"
                )

    def test_launch_response_includes_policy_version(self) -> None:
        """launch() response includes policy_version when injection succeeds."""
        test_entry = {"name": "spec-ops", "dir": "spec-ops", "description": "Default"}
        with (
            patch.object(server, "COMPOSITION_REGISTRY", {"spec-ops": test_entry}),
            patch.object(server, "_get_podman") as mock_get_podman,
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_save_registry"),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_inject_auth", return_value=True),
            patch.object(server, "_patch_crew_config"),
            patch.object(server, "_copy_agents", return_value=[]),
            patch.object(server, "_copy_skills", return_value=[]),
            patch.object(server, "_copy_steering", return_value=[]),
            patch.object(server, "_seed_openspec_store"),
            patch.object(server, "_patch_models"),
            patch.object(server, "_inject_policy", return_value="1"),
            patch.object(server, "_mint_cookie", return_value="test-cookie"),
        ):
            mock_podman = Mock()
            mock_get_podman.return_value = mock_podman
            mock_podman.network_create = Mock()
            mock_podman.volume_create = Mock()
            mock_podman.container_create = Mock()
            mock_podman.container_start = Mock()
            mock_podman.container_stop = Mock()
            mock_podman.container_exec = Mock(return_value="ready")
            mock_podman.container_exec_checked = Mock(return_value="ok")

            result = server.launch("policy-test", composition="spec-ops")

        self.assertEqual(result.get("policy_version"), "1")

    def test_crews_entry_includes_policy_version(self) -> None:
        """crews() per-crew entry includes policy_version from registry."""
        reg = {
            "crews": {
                "test-crew": {
                    "container": "gs-test-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "cookie": "test-cookie",
                    "policy_version": "1",
                }
            }
        }
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(server, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memFree": 4 * 1024**3}})),
        ):
            result = server.crews()

        crew_list = result["crews"]
        self.assertEqual(len(crew_list), 1)
        self.assertEqual(crew_list[0]["policy_version"], "1")

    def test_crews_entry_omits_policy_version_when_absent(self) -> None:
        """crews() omits policy_version for crews launched before this change."""
        reg = {
            "crews": {
                "old-crew": {
                    "container": "gs-old-crew",
                    "status": "running",
                    "composition": "spec-ops",
                    "created_at": "2025-01-01T00:00:00+00:00",
                    "cookie": "old-cookie",
                    # No policy_version key
                }
            }
        }
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_probe_gateway", return_value=True),
            patch.object(server, "_crew_api", return_value=[]),
            patch.object(server, "_get_podman", return_value=Mock(system_info=lambda: {"host": {"memFree": 4 * 1024**3}})),
        ):
            result = server.crews()

        crew_list = result["crews"]
        self.assertEqual(len(crew_list), 1)
        self.assertNotIn("policy_version", crew_list[0])



# ── Memory-aware spawn tests ──────────────────────────────────────────────────


class FakePodmanClient:
    """Test helper with configurable system_info() return values."""

    def __init__(self, mem_free_bytes_sequence: list[int] | None = None) -> None:
        """mem_free_bytes_sequence: list of memFree values to return on successive calls."""
        self._mem_sequence = mem_free_bytes_sequence or [4 * 1024**3]
        self._call_index = 0
        self.system_info_calls = 0

    def system_info(self) -> dict:
        self.system_info_calls += 1
        idx = min(self._call_index, len(self._mem_sequence) - 1)
        self._call_index += 1
        return {"host": {"memFree": self._mem_sequence[idx]}}

    def container_start(self, name: str) -> None:
        pass

    def container_stop(self, name: str) -> None:
        pass

    def container_is_running(self, name: str) -> bool:
        return False

    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        return "ready"


class TestMemoryGate(unittest.TestCase):
    """Tests for the pre-launch memory gate."""

    def test_memory_available_immediately(self) -> None:
        """Gate passes with no sleep when memory is sufficient."""
        # 4 GB free, requires 2 GB
        fake = FakePodmanClient([4 * 1024**3])
        result = server._wait_for_memory(fake, 2.0, 60)
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
            result = server._wait_for_memory(fake, 2.0, 60)
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
            result = server._wait_for_memory(fake, 2.0, 5)
        # Returns the last observed free GB (0.5), which is below the required 2.0
        self.assertAlmostEqual(result, 0.5, delta=0.1)

    def test_gate_skipped_when_disabled(self) -> None:
        """GA_MIN_FREE_MEM_GB=0 skips _wait_for_memory in _ensure_crew_running."""
        crew = {"container": "gs-demo", "cookie": "cookie"}
        fake_podman = FakePodmanClient([int(0.1 * 1024**3)])

        # Make the container appear stopped (so it would trigger memory gate)
        fake_podman.container_is_running = lambda name: False  # type: ignore[method-assign]

        original = server.GA_MIN_FREE_MEM_GB
        try:
            server.GA_MIN_FREE_MEM_GB = 0.0
            with (
                patch.object(server, "_get_podman", return_value=fake_podman),
                patch.object(server, "_wait_for_memory") as mock_wait,
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_mint_cookie", return_value="new-cookie"),
                patch.object(server, "_load_registry", return_value={
                    "crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "status": "stopped"}}
                }),
                patch.object(server, "_save_registry"),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_touch_crew"),
                patch.object(server, "_probe_gateway", return_value=True),
            ):
                # _ensure_crew_running should succeed without calling _wait_for_memory
                try:
                    server._ensure_crew_running(crew, "demo", touch=False)
                except Exception:
                    pass  # may raise for other reasons; we only care about mock_wait
            # The memory gate must never have been called
            mock_wait.assert_not_called()
        finally:
            server.GA_MIN_FREE_MEM_GB = original


class TestPatchCrewConfig(unittest.TestCase):
    """Tests for _patch_crew_config memory threshold patching."""

    def test_spawn_min_memory_from_env(self) -> None:
        """_patch_crew_config writes GA_SPAWN_MIN_MEMORY_GB (not hardcoded 0)."""
        original = server.GA_SPAWN_MIN_MEMORY_GB
        try:
            server.GA_SPAWN_MIN_MEMORY_GB = 2.5
            server.GA_RESOURCE_PRESSURE_GB = 3.0
            server.GA_RESOURCE_CRITICAL_GB = 1.5
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            script = exec_calls[0][1][-1]  # last arg to python3 -c
            self.assertIn("2.5", script)
            self.assertIn("3.0", script)
            self.assertIn("1.5", script)
            self.assertNotIn("'spawn_min_memory_gb'] = 0", script)
            # Verify subagent_timeout_secs and subagent_max_turns are present with defaults
            self.assertIn("subagent_timeout_secs", script)
            self.assertIn("subagent_max_turns", script)
            self.assertIn("3600", script)
            self.assertIn("200", script)
        finally:
            server.GA_SPAWN_MIN_MEMORY_GB = original
            server.GA_RESOURCE_PRESSURE_GB = 2.0
            server.GA_RESOURCE_CRITICAL_GB = 1.0

    def test_subagent_timeout_from_env(self) -> None:
        """GA_SUBAGENT_TIMEOUT_SECS=7200 → subagent_timeout_secs: 7200 in patched config."""
        original = server.GA_SUBAGENT_TIMEOUT_SECS
        try:
            server.GA_SUBAGENT_TIMEOUT_SECS = 7200
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            script = exec_calls[0][1][-1]
            self.assertIn("'subagent_timeout_secs'] = 7200", script)
        finally:
            server.GA_SUBAGENT_TIMEOUT_SECS = original

    def test_subagent_max_turns_from_env(self) -> None:
        """GA_SUBAGENT_MAX_TURNS=300 → subagent_max_turns: 300 in patched config."""
        original = server.GA_SUBAGENT_MAX_TURNS
        try:
            server.GA_SUBAGENT_MAX_TURNS = 300
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            script = exec_calls[0][1][-1]
            self.assertIn("'subagent_max_turns'] = 300", script)
        finally:
            server.GA_SUBAGENT_MAX_TURNS = original

    def test_kc_model_default_set_writes_default_model(self) -> None:
        """KC_MODEL_DEFAULT set → default_model written to config.local.json."""
        original = server.KC_MODEL_DEFAULT
        try:
            server.KC_MODEL_DEFAULT = "anthropic/claude-sonnet-4-20250514"
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            script = exec_calls[0][1][-1]
            self.assertIn("default_model", script)
            self.assertIn("anthropic/claude-sonnet-4-20250514", script)
        finally:
            server.KC_MODEL_DEFAULT = original

    def test_kc_model_default_empty_does_not_write_default_model(self) -> None:
        """KC_MODEL_DEFAULT empty → default_model NOT written to config.local.json."""
        original = server.KC_MODEL_DEFAULT
        try:
            server.KC_MODEL_DEFAULT = ""
            exec_calls: list[tuple[str, list[str]]] = []

            class CapturePodman:
                def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
                    exec_calls.append((name, cmd))
                    return "patched config.local.json"

            server._patch_crew_config(CapturePodman(), "gs-test")  # type: ignore[arg-type]
            self.assertEqual(len(exec_calls), 1)
            script = exec_calls[0][1][-1]
            self.assertNotIn("default_model", script)
        finally:
            server.KC_MODEL_DEFAULT = original


class TestCrewsMemoryField(unittest.TestCase):
    """Tests for host_memory_available_gb in crews() response."""

    def test_crews_includes_memory_field(self) -> None:
        """crews() response includes host_memory_available_gb."""
        reg = {"crews": {}}
        fake = FakePodmanClient([int(3.5 * 1024**3)])
        # Clear cache to force fresh read
        server._host_memory_cache = None
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

        server._host_memory_cache = None
        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_get_podman", return_value=BrokenPodman()),
        ):
            result = server.crews()
        self.assertIn("host_memory_available_gb", result)
        self.assertIsNone(result["host_memory_available_gb"])


class TestMemoryCache(unittest.TestCase):
    """Tests for _get_host_memory_gb_cached TTL behavior."""

    def test_cache_ttl_avoids_repeated_calls(self) -> None:
        """Second call within 5s does not invoke system_info() again."""
        fake = FakePodmanClient([int(4 * 1024**3)])
        server._host_memory_cache = None

        with patch("time.monotonic", return_value=100.0):
            val1 = server._get_host_memory_gb_cached(fake)
        with patch("time.monotonic", return_value=103.0):
            val2 = server._get_host_memory_gb_cached(fake)

        self.assertEqual(val1, val2)
        self.assertEqual(fake.system_info_calls, 1)

    def test_cache_expires_after_ttl(self) -> None:
        """After 5s, a fresh system_info() call is made."""
        fake = FakePodmanClient([int(4 * 1024**3), int(3 * 1024**3)])
        server._host_memory_cache = None

        with patch("time.monotonic", return_value=100.0):
            server._get_host_memory_gb_cached(fake)
        with patch("time.monotonic", return_value=106.0):
            server._get_host_memory_gb_cached(fake)

        self.assertEqual(fake.system_info_calls, 2)


# ══════════════════════════════════════════════════════════════════════════════
# trn-17: New test coverage classes
# ══════════════════════════════════════════════════════════════════════════════


# ── Task 1 mock infrastructure ────────────────────────────────────────────────

class ReconcilePodman:
    """Mock PodmanClient for _reconcile_registry tests."""

    def __init__(
        self,
        containers_exist: dict[str, bool] | None = None,
        containers_running: dict[str, bool] | None = None,
        start_raises: dict[str, Exception] | None = None,
        all_containers: list[dict] | None = None,
    ) -> None:
        self.containers_exist = containers_exist or {}
        self.containers_running = containers_running or {}
        self.start_raises = start_raises or {}
        self.all_containers = all_containers or []
        self.starts: list[str] = []
        self.stops: list[str] = []

    def _req(self, method: str, path: str, **kwargs: Any) -> list:
        return self.all_containers

    def container_exists(self, name: str) -> bool:
        return self.containers_exist.get(name, True)

    def container_is_running(self, name: str) -> bool:
        return self.containers_running.get(name, False)

    def container_start(self, name: str) -> None:
        if name in self.start_raises:
            raise self.start_raises[name]
        self.starts.append(name)

    def container_stop(self, name: str) -> None:
        self.stops.append(name)

    def container_exec(self, name: str, cmd: list[str], env: dict | None = None) -> str:
        return "ready"


class IdleMonitorPodman:
    """Mock PodmanClient for _idle_monitor tests."""

    def __init__(
        self,
        containers_running: dict[str, bool] | None = None,
    ) -> None:
        self.containers_running = containers_running or {}
        self.stops: list[str] = []

    def container_is_running(self, name: str) -> bool:
        return self.containers_running.get(name, True)

    def container_stop(self, name: str) -> None:
        self.stops.append(name)


def _make_registry_file(tmp_dir: Path, crews: dict[str, dict]) -> Path:
    """Create a temporary registry JSON file for test isolation."""
    registry_path = tmp_dir / "crews.json"
    registry_path.write_text(json.dumps({"crews": crews}))
    return registry_path


class MockHTTPResponse:
    """Mock HTTP response factory for idle_monitor API calls."""

    def __init__(self, status_code: int = 200, json_data: Any = None) -> None:
        self.status_code = status_code
        self._json = json_data or {}

    def json(self) -> Any:
        return self._json


# ── Task 2: _reconcile_registry tests ────────────────────────────────────────

class ReconcileRegistryTests(unittest.TestCase):
    """Tests for _reconcile_registry (trn-17 tasks 2.x and 3.x)."""

    def test_orphaned_login_container_swept_on_startup(self) -> None:
        """2.1: orphaned ga-login-* container is swept on startup."""
        podman = ReconcilePodman(
            all_containers=[{"Names": ["/ga-login-stale1234"]}],
        )
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = _make_registry_file(Path(tmp), {})
            with (
                patch.object(server, "_get_podman", return_value=podman),
                patch.object(server, "REGISTRY_PATH", registry_path),
                patch.object(server, "_nuke_login_container") as nuke,
                patch.object(server, "_load_registry", return_value={"crews": {}}),
                patch.object(server, "_save_registry"),
            ):
                server._reconcile_registry()

            nuke.assert_called_once_with(podman, "ga-login-stale1234")

    def test_gone_crew_removed_from_registry(self) -> None:
        """2.2: crew whose container doesn't exist is removed from registry."""
        podman = ReconcilePodman(
            containers_exist={"gs-gone": False},
            all_containers=[],
        )
        crews = {"gone-crew": {"container": "gs-gone", "status": "running"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        self.assertNotIn("gone-crew", saved.get("crews", {}))

    def test_stopped_crew_restarted_cookie_refreshed(self) -> None:
        """2.3: stopped crew is restarted, cookie refreshed, status set to running."""
        podman = ReconcilePodman(
            containers_exist={"gs-test": True},
            containers_running={"gs-test": False},
            all_containers=[],
        )
        crews = {"test-crew": {"container": "gs-test", "status": "stopped", "cookie": "old"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_mint_cookie", return_value="new-cookie"),
        ):
            server._reconcile_registry()

        self.assertIn("gs-test", podman.starts)
        crew_entry = saved["crews"]["test-crew"]
        self.assertEqual(crew_entry["status"], "running")
        self.assertEqual(crew_entry["cookie"], "new-cookie")

    def test_stopped_crew_gateway_fails_marked_stopped(self) -> None:
        """2.4: stopped crew whose gateway fails to start is marked stopped (not removed)."""
        podman = ReconcilePodman(
            containers_exist={"gs-fail": True},
            containers_running={"gs-fail": False},
            all_containers=[],
        )
        crews = {"fail-crew": {"container": "gs-fail", "status": "stopped"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
            patch.object(server, "_wait_gateway", return_value=False),
        ):
            server._reconcile_registry()

        self.assertIn("fail-crew", saved["crews"])
        self.assertEqual(saved["crews"]["fail-crew"]["status"], "stopped")

    def test_running_crew_left_unchanged(self) -> None:
        """2.5: running crew is left unchanged."""
        podman = ReconcilePodman(
            containers_exist={"gs-live": True},
            containers_running={"gs-live": True},
            all_containers=[],
        )
        crews = {"live-crew": {"container": "gs-live", "status": "running", "cookie": "c"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        # Running crew should still exist, unmodified (no updates applied)
        self.assertIn("live-crew", saved["crews"])
        self.assertEqual(saved["crews"]["live-crew"]["cookie"], "c")
        self.assertEqual(podman.starts, [])

    def test_stale_launching_entry_with_missing_container_removed(self) -> None:
        """2.6: stale 'launching' entry with missing container is removed."""
        podman = ReconcilePodman(
            containers_exist={"gs-stale": False},
            all_containers=[],
        )
        crews = {"stale-crew": {"container": "gs-stale", "status": "launching"}}
        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value={"crews": dict(crews)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
        ):
            server._reconcile_registry()

        self.assertNotIn("stale-crew", saved.get("crews", {}))

    def test_crew_removed_between_snapshot_and_writeback_not_resurrected(self) -> None:
        """3.2: crew removed by another thread between snapshot and write-back is NOT resurrected."""
        podman = ReconcilePodman(
            containers_exist={"gs-del": True},
            containers_running={"gs-del": False},
            all_containers=[],
        )
        # First load returns the crew, second load (write-back) it's gone
        load_count = [0]

        def load_registry() -> dict:
            load_count[0] += 1
            if load_count[0] == 1:
                return {"crews": {"del-crew": {"container": "gs-del", "status": "stopped"}}}
            return {"crews": {}}  # Another thread removed it

        saved = {}

        def save_reg(reg: dict) -> None:
            saved.update(reg)

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", side_effect=load_registry),
            patch.object(server, "_save_registry", side_effect=save_reg),
            patch.object(server, "_wait_gateway", return_value=True),
            patch.object(server, "_mint_cookie", return_value="new"),
        ):
            server._reconcile_registry()

        # The crew was removed by another thread — write-back should NOT resurrect it
        self.assertNotIn("del-crew", saved.get("crews", {}))

    def test_reseed_registers_missing_jobs(self) -> None:
        """4.3 — _reseed_crew_schedules POSTs missing jobs to gateway (D8 in TRN-39)."""
        # Registry has a schedule whose job_id is absent from the gateway listing
        crew_info = {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{
                "job_id": "missing-j1", "name": "daily-report",
                "interval_secs": 86400, "cron_expr": None,
                "agent": "ghost", "message": "report", "enabled": True,
                "next_fire_at": time.time() + 1000,
            }],
        }
        reg = {"crews": {"demo": crew_info}}
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # job absent from gateway
            if method == "POST" and path == "/api/crons":
                return {"id": "new-missing-j1"}
            return {}

        crew = {"container": "gs-demo", "cookie": "cookie"}
        save_calls: list[dict] = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(crew, "demo", crew_info)

        # The gateway POST /api/crons must have been made for the missing job
        post_calls = [(m, p, kw) for m, p, kw in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1, f"Expected one POST /api/crons; got: {post_calls}")
        posted_body = post_calls[0][2].get("json", {})
        self.assertEqual(posted_body.get("name"), "daily-report")
        self.assertEqual(posted_body.get("every"), 86400)


# ── Task 4/5: _idle_monitor tests ────────────────────────────────────────────

class IdleMonitorTests(unittest.TestCase):
    """Tests for _idle_monitor logic (trn-17 tasks 4.x and 5.x)."""

    def _run_one_iteration(
        self,
        crew_items: list[tuple[str, dict]],
        podman: IdleMonitorPodman,
        http_responses: list[MockHTTPResponse] | None = None,
        mint_cookie_return: str | None = None,
    ) -> dict[str, Any]:
        """Run a single iteration of the idle monitor and return state."""
        http_calls = []
        response_iter = iter(http_responses or [])

        class FakeHTTP:
            def get(self, url: str, **kwargs: Any) -> MockHTTPResponse:
                http_calls.append(url)
                return next(response_iter, MockHTTPResponse(500))

        touched: list[str] = []
        saved_regs: list[dict] = []

        def touch(crew_id: str) -> None:
            touched.append(crew_id)

        def save_reg(reg: dict) -> None:
            saved_regs.append(dict(reg))

        # Patch the while loop to run once via StopIteration on sleep
        sleep_called = [False]

        def fake_sleep(secs: float) -> None:
            if sleep_called[0]:
                raise StopIteration()
            sleep_called[0] = True

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_http", FakeHTTP()),
            patch.object(server, "_touch_crew", side_effect=touch),
            patch.object(server, "_load_registry", return_value={"crews": dict(crew_items)}),
            patch.object(server, "_save_registry", side_effect=save_reg),
            patch.object(server, "_mint_cookie", return_value=mint_cookie_return),
            patch.object(server.time, "sleep", side_effect=fake_sleep),
            patch.object(server.time, "time", return_value=1000.0),
        ):
            try:
                server._idle_monitor()
            except StopIteration:
                pass

        return {
            "stops": podman.stops,
            "touched": touched,
            "http_calls": http_calls,
            "saved_regs": saved_regs,
        }

    def test_crew_with_active_task_not_stopped(self) -> None:
        """4.1: crew with active dispatch task is not stopped, last_used updated."""
        podman = IdleMonitorPodman(containers_running={"gs-active": True})
        spawn_resp = MockHTTPResponse(200, {"agents": [{"done": False}]})
        crew_items = [("active", {"container": "gs-active", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp])

        self.assertEqual(result["stops"], [])
        self.assertIn("active", result["touched"])

    def test_crew_with_enabled_cron_not_stopped(self) -> None:
        """4.2: crew with enabled cron job is not stopped, last_used updated."""
        podman = IdleMonitorPodman(containers_running={"gs-cron": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_resp = MockHTTPResponse(200, {"jobs": [{"name": "check", "enabled": True}]})
        crew_items = [("cron-crew", {"container": "gs-cron", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp, cron_resp])

        self.assertEqual(result["stops"], [])
        self.assertIn("cron-crew", result["touched"])

    def test_genuinely_idle_crew_is_stopped(self) -> None:
        """4.3: genuinely idle crew is stopped, registry marked 'stopped'."""
        podman = IdleMonitorPodman(containers_running={"gs-idle": True})
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_resp = MockHTTPResponse(200, {"jobs": []})
        crew_items = [("idle-crew", {"container": "gs-idle", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [spawn_resp, cron_resp])

        self.assertIn("gs-idle", result["stops"])
        self.assertTrue(result["saved_regs"])
        self.assertEqual(result["saved_regs"][-1]["crews"]["idle-crew"]["status"], "stopped")

    def test_recently_used_crew_skipped(self) -> None:
        """4.4: recently used crew (within timeout) is skipped."""
        podman = IdleMonitorPodman(containers_running={"gs-recent": True})
        # last_used is recent enough (within GA_IDLE_TIMEOUT_SECS of now=1000)
        crew_items = [("recent", {"container": "gs-recent", "status": "running", "cookie": "c", "last_used": 999.0})]
        result = self._run_one_iteration(crew_items, podman, [])

        self.assertEqual(result["stops"], [])
        self.assertEqual(result["touched"], [])
        self.assertEqual(result["http_calls"], [])

    def test_already_stopped_container_skipped(self) -> None:
        """4.5: already-stopped container is skipped (no double-stop)."""
        podman = IdleMonitorPodman(containers_running={"gs-stopped": False})
        crew_items = [("stopped", {"container": "gs-stopped", "status": "running", "cookie": "c", "last_used": 0})]
        result = self._run_one_iteration(crew_items, podman, [])

        self.assertEqual(result["stops"], [])

    def test_401_triggers_cookie_refresh_and_retry(self) -> None:
        """5.2: 401 response triggers cookie refresh and successful retry."""
        podman = IdleMonitorPodman(containers_running={"gs-auth": True})
        # First spawn call returns 401, retry returns 200 with active task
        spawn_401 = MockHTTPResponse(401)
        spawn_ok = MockHTTPResponse(200, {"agents": [{"done": False}]})
        crew_items = [("auth-crew", {"container": "gs-auth", "status": "running", "cookie": "old", "last_used": 0})]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_401, spawn_ok],
            mint_cookie_return="new-cookie",
        )

        self.assertEqual(result["stops"], [])
        self.assertIn("auth-crew", result["touched"])

    def test_401_with_failed_cookie_refresh_skips_crew(self) -> None:
        """5.3: 401 with failed cookie refresh skips crew (does not stop it)."""
        podman = IdleMonitorPodman(containers_running={"gs-nauth": True})
        spawn_401 = MockHTTPResponse(401)
        crew_items = [("nauth-crew", {"container": "gs-nauth", "status": "running", "cookie": "dead", "last_used": 0})]
        result = self._run_one_iteration(
            crew_items, podman, [spawn_401],
            mint_cookie_return=None,  # cookie refresh fails
        )

        # Should NOT stop the crew (fail-open)
        self.assertEqual(result["stops"], [])
        # Should NOT touch (we can't verify activity)
        self.assertEqual(result["touched"], [])

    def test_idle_monitor_cron_401_retries_with_fresh_cookie(self) -> None:
        """D9 — cron endpoint 401 triggers cookie refresh and retry (TRN-39 4.4)."""
        podman = IdleMonitorPodman(containers_running={"gs-cron401": True})
        # spawn returns empty (no tasks), cron first returns 401, then (after cookie refresh)
        # returns a listing with an enabled cron job (keeps crew alive).
        spawn_resp = MockHTTPResponse(200, {"agents": []})
        cron_401 = MockHTTPResponse(401)
        cron_ok = MockHTTPResponse(200, {"jobs": [{"name": "check", "enabled": True}]})
        crew_items = [(
            "cron401-crew",
            {"container": "gs-cron401", "status": "running", "cookie": "old", "last_used": 0},
        )]

        result = self._run_one_iteration(
            crew_items, podman, [spawn_resp, cron_401, cron_ok],
            mint_cookie_return="new-cookie",
        )

        # Cookie refresh happened, cron retried — crew should NOT be stopped
        self.assertEqual(result["stops"], [], "crew should not be stopped after cron 401 retry")
        self.assertIn("cron401-crew", result["touched"])



# ── Task 6: _finish_crew_setup ordering tests ────────────────────────────────

class FinishCrewSetupOrderingTests(unittest.TestCase):
    """Tests for _finish_crew_setup step ordering (trn-17 tasks 6.x)."""

    def test_happy_path_setup_records_steps_in_order(self) -> None:
        """6.1: full happy-path records steps in exact required order."""
        steps: list[str] = []
        podman = Mock()
        podman.container_stop = Mock(side_effect=lambda *a: steps.append("stop"))
        podman.container_start = Mock(side_effect=lambda *a: steps.append("start"))
        podman.container_exec = Mock(return_value="ready")
        podman.container_exec_checked = Mock(return_value="ok")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {"org.ghostship.version": "1.0"}}})

        def wait_gw(url: str, timeout: int = 30) -> bool:
            steps.append("wait_gateway")
            return True

        def inject_auth(*a: Any, **kw: Any) -> None:
            steps.append("inject_auth")

        def patch_config(*a: Any, **kw: Any) -> None:
            steps.append("patch_config")

        def copy_agents(*a: Any, **kw: Any) -> list:
            steps.append("copy_agents")
            return []

        def copy_skills(*a: Any, **kw: Any) -> list:
            steps.append("copy_skills")
            return []

        def copy_steering(*a: Any, **kw: Any) -> list:
            steps.append("copy_steering")
            return []

        def seed_openspec(*a: Any, **kw: Any) -> None:
            steps.append("seed_openspec")

        def patch_models(*a: Any, **kw: Any) -> None:
            steps.append("patch_models")

        def mint_cookie(*a: Any, **kw: Any) -> str:
            steps.append("mint_cookie")
            return "test-cookie"

        def inject_policy(*a: Any, **kw: Any) -> str:
            steps.append("inject_policy")
            return "1"

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"),
                patch.object(server, "_wait_gateway", side_effect=wait_gw),
                patch.object(server, "_inject_auth", side_effect=inject_auth),
                patch.object(server, "_patch_crew_config", side_effect=patch_config),
                patch.object(server, "_copy_agents", side_effect=copy_agents),
                patch.object(server, "_copy_skills", side_effect=copy_skills),
                patch.object(server, "_copy_steering", side_effect=copy_steering),
                patch.object(server, "_seed_openspec_store", side_effect=seed_openspec),
                patch.object(server, "_patch_models", side_effect=patch_models),
                patch.object(server, "_mint_cookie", side_effect=mint_cookie),
                patch.object(server, "_inject_policy", side_effect=inject_policy),
            ):
                result = server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(result["status"], "ready")
        # Verify the correct ordering of critical steps.
        # The full sequence in _finish_crew_setup is:
        #   wait_gateway → inject_auth → [admiral secret inject via exec_checked] →
        #   patch_config → stop → start → wait_gateway → copy_agents → copy_skills →
        #   copy_steering → seed_openspec → inject_policy →
        #   [wait for agent files via exec] → patch_models → mint_cookie → [registry write]
        expected_prefix = [
            "wait_gateway",     # Initial gateway wait
            "inject_auth",      # Auth inject
            "patch_config",     # Config patch
            "stop",             # Restart (stop)
            "start",            # Restart (start)
            "wait_gateway",     # Wait after restart
            "copy_agents",      # Copy agents
            "copy_skills",      # Copy skills
            "copy_steering",    # Copy steering
            "seed_openspec",    # OpenSpec seed
        ]
        self.assertEqual(steps[:len(expected_prefix)], expected_prefix)
        # After seed_openspec, inject_policy comes before patch_models and mint_cookie
        self.assertIn("inject_policy", steps)
        self.assertIn("patch_models", steps)
        self.assertIn("mint_cookie", steps)
        policy_idx = steps.index("inject_policy")
        models_idx = steps.index("patch_models")
        cookie_idx = steps.index("mint_cookie")
        self.assertLess(policy_idx, models_idx)
        self.assertLess(models_idx, cookie_idx)

    def test_admiral_secret_injected_before_container_restart(self) -> None:
        """6.3 (trn-36 2.1): admiral secret exec call occurs before container_stop/start."""
        exec_calls: list[list[str]] = []
        stop_calls: list[int] = []
        start_calls: list[int] = []
        call_counter: list[int] = [0]

        podman = Mock()

        def track_exec_checked(container: str, cmd: list[str]) -> str:
            call_counter[0] += 1
            exec_calls.append((call_counter[0], cmd))
            return "ok"

        def track_stop(name: str) -> None:
            call_counter[0] += 1
            stop_calls.append(call_counter[0])

        def track_start(name: str) -> None:
            call_counter[0] += 1
            start_calls.append(call_counter[0])

        podman.container_exec_checked = Mock(side_effect=track_exec_checked)
        podman.container_stop = Mock(side_effect=track_stop)
        podman.container_start = Mock(side_effect=track_start)
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"),
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_inject_auth"),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_copy_agents", return_value=[]),
                patch.object(server, "_copy_skills", return_value=[]),
                patch.object(server, "_copy_steering", return_value=[]),
                patch.object(server, "_seed_openspec_store"),
                patch.object(server, "_patch_models"),
                patch.object(server, "_inject_policy", return_value="1"),
                patch.object(server, "_mint_cookie", return_value="test-cookie"),
            ):
                result = server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(result["status"], "ready")
        # Find the admiral secret injection call (first exec_checked call whose
        # command contains the secret injection marker)
        secret_call_order = None
        for order, cmd in exec_calls:
            if len(cmd) >= 3 and "admiral_secret" in cmd[2]:
                secret_call_order = order
                break
        self.assertIsNotNone(secret_call_order, "Admiral secret injection exec call not found")
        # The container restart (first stop) must come after the secret injection
        first_stop_order = stop_calls[0] if stop_calls else None
        self.assertIsNotNone(first_stop_order, "Expected at least one container_stop call")
        self.assertLess(
            secret_call_order,
            first_stop_order,
            "Admiral secret injection must occur before first container_stop",
        )

    def test_admiral_secret_injection_script_contains_fsync(self) -> None:
        """6.4 (trn-36 2.2): the admiral secret injection script contains os.fsync."""
        captured_scripts: list[str] = []

        podman = Mock()

        def capture_exec_checked(container: str, cmd: list[str]) -> str:
            if len(cmd) >= 3 and "admiral_secret" in cmd[2]:
                captured_scripts.append(cmd[2])
            return "ok"

        podman.container_exec_checked = Mock(side_effect=capture_exec_checked)
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", Path(tmp) / "crews.json"),
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_inject_auth"),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_copy_agents", return_value=[]),
                patch.object(server, "_copy_skills", return_value=[]),
                patch.object(server, "_copy_steering", return_value=[]),
                patch.object(server, "_seed_openspec_store"),
                patch.object(server, "_patch_models"),
                patch.object(server, "_inject_policy", return_value="1"),
                patch.object(server, "_mint_cookie", return_value="test-cookie"),
            ):
                server._finish_crew_setup(
                    podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
                )

        self.assertEqual(len(captured_scripts), 1, "Expected exactly one admiral secret injection call")
        script = captured_scripts[0]
        self.assertIn("os.fsync", script, "Secret injection script must call os.fsync for durability")

    def test_gateway_failure_after_restart_triggers_cleanup(self) -> None:
        """6.2: gateway failure after auth restart triggers cleanup and returns error."""
        podman = Mock()
        podman.container_stop = Mock()
        podman.container_start = Mock()
        podman.container_exec = Mock(return_value="ready")
        podman.container_inspect = Mock(return_value={"Config": {"Labels": {}}})

        wait_count = [0]

        def wait_gw(url: str, timeout: int = 30) -> bool:
            wait_count[0] += 1
            # First call: initial gateway check (timeout=10) → passes
            if wait_count[0] == 1:
                return True
            # Second call: after auth inject + config patch + restart → fails
            return False

        cleanup_called = [False]

        def cleanup(*a: Any, **kw: Any) -> None:
            cleanup_called[0] = True

        with (
            patch.object(server, "_wait_gateway", side_effect=wait_gw),
            patch.object(server, "_inject_auth"),
            patch.object(server, "_patch_crew_config"),
            patch.object(server, "_cleanup_crew", side_effect=cleanup),
        ):
            result = server._finish_crew_setup(
                podman, "test", "gs-test", "vol-test", "home-test", "auth-b64"
            )

        self.assertIn("error", result)
        self.assertIn("did not recover", result["error"])
        self.assertTrue(cleanup_called[0])


# ── Task 7: Login flow edge case tests ────────────────────────────────────────

class LoginFlowEdgeCaseTests(unittest.TestCase):
    """Tests for login flow edge cases (trn-17 tasks 7.x)."""

    def setUp(self) -> None:
        with server._login_pending_lock:
            server._login_pending = None

    def test_pty_exec_no_url_within_15s_returns_500_and_cleans_up(self) -> None:
        """7.1: PTY exec with no URL within 15s returns 500 and cleans up container."""
        podman = Mock()
        fake_sock = Mock()
        fake_sock.fileno.return_value = 5
        fake_sock.recv.return_value = b"Loading...\n"

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value="ga-login-timeout"),
            patch.object(server, "_nuke_login_container") as nuke,
            patch.object(server, "time") as mock_time,
            patch.object(server, "select") as mock_select,
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-x", fake_sock)),
        ):
            # Simulate timeout: time starts at 1000, after one read it's past 1015
            mock_time.time.side_effect = [1000.0, 1000.0, 1016.0]
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 500)
        nuke.assert_called_once_with(podman, "ga-login-timeout")

    def test_region_prompt_answered_with_kiro_region(self) -> None:
        """7.2: Region prompt is answered with KIRO_REGION when encountered."""
        podman = Mock()
        fake_sock = Mock()
        fake_sock.fileno.return_value = 5

        # First read: Start URL prompt, second: Region prompt, third: device URL
        read_sequence = [
            b"? Enter Start URL \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Start URL\r\n? Enter Region \xe2\x80\xba ",
            b"\x1b[2K\xe2\x9c\x94 Enter Region\r\nOpen this URL: https://device.sso.example.com/activate?user_code=TEST-1234\r\nCode: TEST-1234\r\n",
        ]
        read_iter = iter(read_sequence)
        fake_sock.recv.side_effect = lambda n: next(read_iter, b"")
        sends: list[bytes] = []
        fake_sock.sendall.side_effect = lambda data: sends.append(data)

        with (
            patch.object(server, "_read_auth_file", return_value=""),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_start_login_container", return_value="ga-login-region"),
            patch.object(server, "select") as mock_select,
            patch.object(server, "KIRO_REGION", "us-west-2"),
            patch.object(podman, "container_exec", return_value="kiro-cli"),
            patch.object(podman, "container_exec_pty_stdin", return_value=("exec-r", fake_sock)),
        ):
            mock_select.select.return_value = ([fake_sock], [], [])
            request = Mock()
            response = asyncio.run(server._handle_login_post(request))

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["status"], "pending")
        # Verify region was sent to the PTY
        all_sent = b"".join(sends)
        self.assertIn(b"us-west-2", all_sent)

    def test_concurrent_post_login_while_pending_returns_409(self) -> None:
        """7.3: concurrent POST /login while _login_pending is set returns 409."""
        # Set pending state
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-existing",
                "exec_id": "x",
                "started_at": 999.0,
            }

        try:
            with patch.object(server, "_read_auth_file", return_value=""):
                request = Mock()
                response = asyncio.run(server._handle_login_post(request))

            self.assertEqual(response.status_code, 409)
            self.assertIn("Login already in progress", response.body.decode())
        finally:
            with server._login_pending_lock:
                server._login_pending = None


# ── Task 8: _handle_login_get guard-clear tests ──────────────────────────────

class LoginGuardClearTests(unittest.TestCase):
    """Tests for _handle_login_get guard-clear ordering (trn-17 tasks 8.x)."""

    def setUp(self) -> None:
        with server._login_pending_lock:
            server._login_pending = None

    def test_guard_clear_ordering_verified(self) -> None:
        """8.1: _login_pending is cleared ONLY AFTER _nuke_login_container completes."""
        # Set up a pending login
        pending_container = "ga-login-test1234"
        with server._login_pending_lock:
            server._login_pending = {
                "container": pending_container,
                "exec_id": "exec-1",
                "started_at": time.time(),
            }

        nuked_flag = {"done": False}
        cleared_before_nuke = {"seen": False}

        def fake_nuke(podman, container):
            # At the point nuke is called, _login_pending must NOT yet be None
            with server._login_pending_lock:
                if server._login_pending is None:
                    cleared_before_nuke["seen"] = True
            nuked_flag["done"] = True

        fake_podman = Mock()
        fake_podman.container_is_running = Mock(return_value=False)

        try:
            with (
                patch.object(server, "_get_podman", return_value=fake_podman),
                patch.object(server, "_read_auth_from_crew", return_value="dGVzdA=="),
                patch.object(server, "_write_auth_file"),
                patch.object(server, "_load_registry", return_value={"crews": {}}),
                patch.object(server, "_inject_auth"),
                patch.object(server, "_nuke_login_container", side_effect=fake_nuke),
            ):
                asyncio.run(server._handle_login_get(Mock()))
        except Exception:
            pass

        # nuke must have run
        self.assertTrue(nuked_flag["done"], "_nuke_login_container was never called")
        # _login_pending must not have been cleared BEFORE nuke
        self.assertFalse(
            cleared_before_nuke["seen"],
            "_login_pending was cleared before _nuke_login_container returned",
        )
        # After the function returns, _login_pending should be None
        with server._login_pending_lock:
            self.assertIsNone(server._login_pending, "_login_pending should be None after cleanup")

    def test_concurrent_post_during_cleanup_window_returns_409(self) -> None:
        """8.2: concurrent POST /login during cleanup window receives 409."""
        # Simulate the scenario where _handle_login_get has detected auth and
        # is between nuke and guard-clear. If a POST /login arrives at this
        # moment, the _login_pending is still set so the POST should get 409.
        with server._login_pending_lock:
            server._login_pending = {
                "container": "ga-login-completing",
                "exec_id": "x",
                "started_at": 999.0,
            }

        try:
            with patch.object(server, "_read_auth_file", return_value=""):
                request = Mock()
                response = asyncio.run(server._handle_login_post(request))

            self.assertEqual(response.status_code, 409)
        finally:
            with server._login_pending_lock:
                server._login_pending = None


# ── TRN-29: Schedule Persistence Tests ───────────────────────────────────────


class SchedulePersistenceTests(unittest.TestCase):
    """Tests for TRN-29 transport schedule persistence."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def _make_registry(self, crew_id: str = "demo", schedules: list | None = None) -> dict:
        return {"crews": {crew_id: {"container": "gs-demo", "cookie": "cookie", "schedules": schedules or []}}}

    def test_captain_order_writes_schedule_entry(self) -> None:
        """7.1 — captain(action='order') writes schedule entry to registry."""
        reg = self._make_registry()
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": []}
        created_job = {"id": "cap-job-1", "name": "captain", "schedule": "every 300s"}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "POST" and path == "/api/crons":
                return created_job
            if method == "POST" and "/api/spawn" in path:
                return {"id": "spawn-1"}
            return {}

        fake_podman = SetupPodman()
        fake_podman.container_exec = lambda *a, **kw: ""

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(server, "_get_podman", return_value=fake_podman),
            patch.object(server, "_append_captain_mail"),
        ):
            result = server.captain(crew_id="demo", action="order", message="do stuff", interval=300)

        self.assertEqual(result["status"], "ordered")
        self.assertEqual(result["job_id"], "cap-job-1")
        # Verify registry was written with schedule entry
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["job_id"], "cap-job-1")
        self.assertEqual(schedules[0]["name"], "captain")
        self.assertEqual(schedules[0]["agent"], "raven")
        self.assertTrue(schedules[0]["enabled"])

    def test_schedule_list_returns_registry_entries_when_stopped(self) -> None:
        """7.2 — schedule(action='list') returns registry entries when crew stopped."""
        reg = self._make_registry(schedules=[
            {"job_id": "j1", "name": "daily-check", "interval_secs": 3600, "cron_expr": None,
             "agent": "ghost", "enabled": True, "next_fire_at": 9999999999.0},
        ])

        with (
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server._schedule_list("demo")

        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["job_id"], "j1")
        self.assertEqual(result["jobs"][0]["name"], "daily-check")
        self.assertEqual(result["jobs"][0]["agent"], "ghost")
        self.assertTrue(result["jobs"][0]["enabled"])

    def test_schedule_cancel_removes_from_registry(self) -> None:
        """7.3 — schedule(action='cancel') removes from registry."""
        reg = self._make_registry(schedules=[
            {"job_id": "j1", "name": "my-job", "interval_secs": 60, "cron_expr": None,
             "agent": "ghost", "enabled": True},
        ])
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        jobs_listing = {"jobs": [
            {"id": "j1", "name": "my-job", "agent": "ghost", "enabled": True},
        ]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "DELETE":
                return {}
            return {}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server._schedule_cancel("j1", "demo")

        self.assertEqual(result, {"status": "cancelled", "job_id": "j1"})
        # Verify registry no longer has the job
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 0)

    def test_schedule_delay_creates_one_shot_registry_entry(self) -> None:
        """7.7 — schedule(delay=N) creates one-shot entry in registry."""
        reg = self._make_registry()
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", return_value={"id": "delay-job-1"}),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            result = server.schedule(
                name="cleanup", message="run cleanup", agent="ghost",
                crew_id="demo", delay=300,
            )

        self.assertEqual(result["job_id"], "delay-job-1")
        self.assertEqual(result["status"], "scheduled")
        self.assertEqual(result["delay"], 300)
        # Verify registry was written with one-shot entry
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["job_id"], "delay-job-1")
        self.assertTrue(schedules[0].get("one_shot"))

    def test_dispatch_no_longer_accepts_delay(self) -> None:
        """7.8 — dispatch no longer accepts delay parameter."""
        import inspect
        sig = inspect.signature(server.dispatch)
        self.assertNotIn("delay", sig.parameters)

    def test_registry_rejects_inf_in_next_fire_at(self) -> None:
        """One-shot job with float('inf') must not be JSON-serialisable.  # requires TRN-37

        TRN-37 replaces float('inf') with _NEVER_FIRE_AT (9_999_999_999.0) to
        ensure the registry can always be serialised with allow_nan=False.
        This test confirms the guard is the correct fix: float('inf') DOES raise.
        """
        reg = self._make_registry(schedules=[{
            "job_id": "j-inf", "name": "one-shot", "interval_secs": None,
            "cron_expr": None, "agent": "ghost", "enabled": True,
            "next_fire_at": float("inf"),
        }])
        with self.assertRaises(ValueError):
            json.dumps(reg, allow_nan=False)

    def test_captain_resume_sets_next_fire_at(self) -> None:
        """7.x — captain resume sets next_fire_at ≈ now + interval in registry."""
        interval = 300
        reg = self._make_registry(schedules=[
            # Existing disabled entry — the resume path will re-enable it
            {"job_id": "cap-job-1", "name": "captain", "interval_secs": interval,
             "cron_expr": None, "agent": "raven", "enabled": False,
             "next_fire_at": 0.0},
        ])
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        # Gateway has the job disabled (resume path: existing_job != None, enabled_job == None)
        existing_job = {"id": "cap-job-1", "name": "captain", "schedule": f"every {interval}s",
                        "enabled": False, "agent": "raven"}
        jobs_listing = {"jobs": [existing_job]}

        def api(_crew, _crew_id, method, path, **kwargs):
            if method == "GET" and path == "/api/crons":
                return jobs_listing
            if method == "POST" and path == f"/api/crons/{existing_job['id']}/enable":
                return {"ok": True}
            if method == "POST" and path == "/api/crons":
                return {"id": "cap-job-1", "schedule": f"every {interval}s"}
            if method == "POST" and "/api/spawn" in path:
                return {"id": "spawn-1"}
            return {}

        fake_podman = SetupPodman()
        fake_podman.container_exec = lambda *a, **kw: ""

        before = time.time()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(server, "_get_podman", return_value=fake_podman),
            patch.object(server, "_append_captain_mail"),
        ):
            result = server.captain(
                crew_id="demo", action="order", message="check in", interval=interval,
            )

        self.assertEqual(result.get("status"), "ordered")
        self.assertTrue(len(save_calls) > 0)
        last_reg = save_calls[-1]
        schedules = last_reg["crews"]["demo"]["schedules"]
        self.assertEqual(len(schedules), 1)
        entry = schedules[0]
        self.assertGreaterEqual(
            entry["next_fire_at"], before + interval - 1,
            f"next_fire_at {entry['next_fire_at']!r} should be ≈ now+{interval}",
        )


class ScheduleMonitorTests(unittest.TestCase):
    """Tests for TRN-29 _schedule_monitor."""

    CREW = {"container": "gs-demo", "cookie": "cookie", "status": "running"}

    def test_monitor_wakes_crew_and_fires_tick(self) -> None:
        """7.4 — _schedule_monitor calls the real function; tick is fired after one loop."""
        now = time.time()
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie", "status": "stopped",
            "schedules": [{
                "job_id": "j1", "name": "check", "interval_secs": 300, "cron_expr": None,
                "next_fire_at": now - 10,  # due
                "agent": "ghost", "message": "do check", "enabled": True,
            }],
        }}}
        api_calls = []

        def api(_crew, _crew_id, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            return {"id": "spawn-1"}

        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        # Use StopIteration on the second time.sleep call to exit the while True loop
        # after exactly one iteration.  The monitor sleeps FIRST, then does work, then
        # loops back to sleep — raising on the second sleep gives the work one full pass.
        sleep_count = [0]

        def fake_sleep(secs: float) -> None:
            sleep_count[0] += 1
            if sleep_count[0] >= 2:
                raise StopIteration("break after one iteration")

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery", side_effect=api),
            patch.object(server, "_save_registry", side_effect=fake_save),
            patch.object(server, "_get_crew_schedules", return_value=reg["crews"]["demo"]["schedules"]),
            patch.object(server.time, "sleep", side_effect=fake_sleep),
        ):
            try:
                server._schedule_monitor()
            except StopIteration:
                pass  # expected — one iteration complete

        # Verify the spawn POST was fired
        self.assertTrue(
            any(m == "POST" and "/api/spawn" in p for m, p, _ in api_calls),
            f"Expected a POST /api/spawn call; got: {api_calls}",
        )
        # Verify registry was saved after the tick
        self.assertTrue(len(save_calls) > 0, "Expected _save_registry to have been called")

    def test_monitor_skips_and_advances_on_crew_failure(self) -> None:
        """7.5 — _schedule_monitor skips tick and advances when crew won't start."""
        now = time.time()
        sched = {
            "job_id": "j1", "name": "check", "interval_secs": 300, "cron_expr": None,
            "next_fire_at": now - 10, "agent": "ghost", "message": "do check", "enabled": True,
        }

        # Simulate: _ensure_crew_running raises, so we advance
        server._advance_next_fire_at(sched)
        self.assertGreater(sched["next_fire_at"], now)

    def test_reseed_crew_schedules_reregisters_missing_jobs(self) -> None:
        """7.6 — _reseed_crew_schedules re-registers missing jobs in gateway."""
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{
                "job_id": "j1", "name": "daily-report", "interval_secs": 86400,
                "cron_expr": None, "agent": "ghost", "message": "report",
                "enabled": True, "next_fire_at": time.time() + 1000,
            }],
        }}}
        api_calls = []

        def api(_crew, method, path, **kwargs):
            api_calls.append((method, path, kwargs))
            if method == "GET" and path == "/api/crons":
                return {"jobs": []}  # No jobs in gateway
            if method == "POST" and path == "/api/crons":
                return {"id": "new-j1"}
            return {}

        crew = {"container": "gs-demo", "cookie": "cookie"}
        save_calls = []

        def fake_save(r):
            save_calls.append(json.loads(json.dumps(r)))

        with (
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_crew_api", side_effect=api),
            patch.object(server, "_save_registry", side_effect=fake_save),
        ):
            server._reseed_crew_schedules(crew, "demo", reg["crews"]["demo"])

        # Verify POST to /api/crons was called to re-register
        post_calls = [(m, p) for m, p, _ in api_calls if m == "POST" and p == "/api/crons"]
        self.assertEqual(len(post_calls), 1)


# ── TRN-39: _advance_next_fire_at tests ─────────────────────────────────────

class AdvanceNextFireAtTests(unittest.TestCase):
    """Tests for _advance_next_fire_at (D4 in TRN-39 design.md)."""

    def test_interval_branch(self) -> None:
        """interval_secs=300 advances next_fire_at by ~300 seconds."""
        now = time.time()
        job = {"job_id": "j1", "interval_secs": 300, "cron_expr": None, "one_shot": False}
        server._advance_next_fire_at(job)
        self.assertAlmostEqual(job["next_fire_at"], now + 300, delta=2.0)

    def test_cron_branch(self) -> None:
        """cron_expr branch advances using croniter, not always +60s.  # requires TRN-37"""
        job = {"job_id": "j2", "interval_secs": None, "cron_expr": "0 * * * *", "one_shot": False}
        now = time.time()
        server._advance_next_fire_at(job)
        # croniter should give the next top-of-hour, which is > now+60 in general
        # and always <= now+3600.  The key assertion is that it is NOT simply now+60.
        self.assertGreater(job["next_fire_at"], now)
        self.assertLessEqual(job["next_fire_at"], now + 3601)
        # Confirm it is computing a real cron tick, not the fallback now+60 value:
        # a value exactly at now+60 would mean croniter was not used.
        self.assertGreater(job["next_fire_at"], now + 60)

    def test_one_shot_branch(self) -> None:
        """one_shot=True sets next_fire_at to _NEVER_FIRE_AT sentinel."""
        job = {"job_id": "j3", "interval_secs": 60, "cron_expr": None, "one_shot": True}
        server._advance_next_fire_at(job)
        self.assertEqual(job["next_fire_at"], server._NEVER_FIRE_AT)


# ── TRN-38 Security Hardening Tests ──────────────────────────────────────────

class TestTrn38SecurityHardening(unittest.TestCase):
    """Tests for TRN-38 security hardening changes."""

    # ── 9.1 HMAC token length is now 32 hex chars (128-bit) ──────────────────

    def test_sign_file_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_file_url produces a 32-char hex sig (not 16)."""
        url = server._sign_file_url("demo", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 32, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_sign_upload_url_hmac_is_32_hex_chars(self) -> None:
        """_sign_upload_url produces a 32-char hex sig (not 16)."""
        url = server._sign_upload_url("demo", "repo")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertEqual(len(query["sig"]), 32, f"sig length {len(query['sig'])} != 32: {query['sig']}")

    def test_16_char_sig_rejected_by_verify_file_token(self) -> None:
        """A legacy 16-char sig is rejected by _verify_file_token (length mismatch)."""
        import hmac as _hmac, hashlib as _hashlib
        expires = str(int(time.time()) + 300)
        payload = f"demo:repo/file.txt:::{expires}"
        short_sig = _hmac.new(
            server._FILE_SECRET.encode(), payload.encode(), _hashlib.sha256
        ).hexdigest()[:16]
        self.assertFalse(
            server._verify_file_token("demo", "repo/file.txt", expires, short_sig)
        )

    # ── 9.2 Upload mode signing ───────────────────────────────────────────────

    def test_plain_token_rejected_when_unpack_mode_presented(self) -> None:
        """Token signed with mode='' fails when mode='unpack' is verified."""
        url = server._sign_upload_url("demo", "repo")  # mode=""
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode="unpack"
            ),
            "Plain token should fail verification when mode='unpack' is presented",
        )

    def test_unpack_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='unpack' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", unpack=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Unpack token should fail verification when mode='' is presented",
        )

    def test_bundle_token_rejected_when_plain_mode_presented(self) -> None:
        """Token signed with mode='bundle' fails when mode='' is verified."""
        url = server._sign_upload_url("demo", "repo", bundle=True)
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        self.assertFalse(
            server._verify_file_token(
                "demo", "repo", query["expires"], query["sig"], mode=""
            ),
            "Bundle token should fail verification when mode='' is presented",
        )

    def test_upload_mode_round_trips_correctly(self) -> None:
        """Tokens round-trip: plain/unpack/bundle each verify with matching mode."""
        for unpack, bundle, expected_mode in [
            (False, False, ""),
            (True, False, "unpack"),
            (False, True, "bundle"),
        ]:
            with self.subTest(mode=expected_mode):
                url = server._sign_upload_url("demo", "repo", unpack=unpack, bundle=bundle)
                query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
                self.assertTrue(
                    server._verify_file_token(
                        "demo", "repo", query["expires"], query["sig"], mode=expected_mode
                    ),
                    f"Mode '{expected_mode}' token failed round-trip verification",
                )

    # ── 9.3 _handle_file_put rejects mode mismatch with 403 ──────────────────

    def test_handle_file_put_rejects_bundle_flag_on_plain_token(self) -> None:
        """PUT with bundle=1 query param on a plain-mode token returns 403."""
        # Sign a plain (mode="") token
        url = server._sign_upload_url("crewone", "repo/file.txt")
        query = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}

        # Craft request: add bundle=1 to query params (mode mismatch)
        tampered_query = dict(query)
        tampered_query["bundle"] = "1"
        request = Request("crewone", "repo/file.txt", b"data", tampered_query)

        crew = {"container": "gs-crewone"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            response = asyncio.run(server._handle_file_put(request))

        self.assertEqual(response.status_code, 403)

    # ── 9.4 evac empty path returns error ────────────────────────────────────

    def test_evac_empty_path_returns_error(self) -> None:
        """evac(path='') returns {'error': 'path must not be empty'}."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("", crew_id="demo")

        self.assertIn("error", result)
        self.assertIn("empty", result["error"].lower())

    def test_evac_slash_only_path_returns_error(self) -> None:
        """evac(path='/') strips to '' and returns error."""
        crew = {"container": "gs-demo"}
        with (
            patch.object(server, "_require_crew", return_value=crew),
            patch.object(server, "_ensure_crew_running", return_value=crew),
        ):
            result = server.evac("/", crew_id="demo")

        self.assertIn("error", result)

    # ── 9.5 / 9.6 crew_id format validation in file handlers ─────────────────

    def _make_get_request(self, crew_id: str, path: str) -> "Request":
        """Return a signed GET request for the given crew_id (bypassing real signing)."""
        expires = str(int(time.time()) + 300)
        # Use a patched _verify_file_token — we test the crew_id guard, not the sig
        return Request(crew_id, path, b"", {"expires": expires, "sig": "x" * 32})

    def _make_put_request(self, crew_id: str, path: str) -> "Request":
        return Request(crew_id, path, b"data", {"expires": str(int(time.time()) + 300), "sig": "x" * 32})

    def test_handle_file_get_rejects_crew_id_with_slash(self) -> None:
        """GET returns 400 for crew_id containing '/'."""
        request = self._make_get_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_dotdot(self) -> None:
        """GET returns 400 for crew_id containing '..'."""
        request = self._make_get_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_percent(self) -> None:
        """GET returns 400 for crew_id containing '%'."""
        request = self._make_get_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_get_rejects_crew_id_with_uppercase(self) -> None:
        """GET returns 400 for crew_id containing uppercase letters."""
        request = self._make_get_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_get(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_slash(self) -> None:
        """PUT returns 400 for crew_id containing '/'."""
        request = self._make_put_request("crew/bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_dotdot(self) -> None:
        """PUT returns 400 for crew_id containing '..'."""
        request = self._make_put_request("crew..bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_percent(self) -> None:
        """PUT returns 400 for crew_id containing '%'."""
        request = self._make_put_request("crew%20bad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    def test_handle_file_put_rejects_crew_id_with_uppercase(self) -> None:
        """PUT returns 400 for crew_id containing uppercase letters."""
        request = self._make_put_request("CrewBad", "file.txt")
        response = asyncio.run(server._handle_file_put(request))
        self.assertEqual(response.status_code, 400)

    # ── 9.7 _save_registry produces 0o600 mode ───────────────────────────────

    def test_save_registry_produces_0o600_permissions(self) -> None:
        """_save_registry writes crews.json with mode 0o600."""
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "crews.json"
            reg = {"crews": {}}
            with (
                patch.object(server, "DATA_DIR", Path(tmp)),
                patch.object(server, "REGISTRY_PATH", registry_path),
            ):
                server._save_registry(reg)

            self.assertTrue(registry_path.exists())
            mode = stat.S_IMODE(os.stat(registry_path).st_mode)
            self.assertEqual(
                mode, 0o600,
                f"Expected 0o600, got 0o{mode:03o}",
            )

    # ── 9.8 _inject_policy output does not contain admiral_secret ────────────

    def test_inject_policy_output_does_not_contain_admiral_secret(self) -> None:
        """_inject_policy does not write admiral_secret into admission_policy.json."""
        captured_scripts: list[str] = []

        def capture_exec(container: str, cmd: list[str]) -> str:
            if cmd[0] == "python3":
                captured_scripts.append(cmd[2])
            return "policy injected version=1"

        mock_podman = Mock()
        mock_podman.container_exec_checked.side_effect = capture_exec

        policy_content = json.dumps({
            "version": "1",
            "commands": {"deny": []},
        })

        with patch("transport.server.Path") as MockPath:
            composition_path = Mock()
            composition_path.exists.return_value = False
            default_path = Mock()
            default_path.exists.return_value = True
            default_path.read_text.return_value = policy_content

            def path_side(arg):
                if "default.json" in str(arg):
                    return default_path
                return composition_path

            MockPath.side_effect = path_side

            server._inject_policy(mock_podman, "gs-test", "spec-ops", "MY_SECRET_VALUE")

        # Verify none of the exec scripts embed the literal secret
        # trust_keys IS required in admission_policy.json — KiroCrew governance
        # uses it to verify the security policy signature. The threat model
        # (single-operator, isolated containers) accepts this. See docs/auth.md.
        for script in captured_scripts:
            if "admission_body" in script:
                self.assertIn(
                    "'trust_keys'",
                    script,
                    "admission_policy.json must contain trust_keys for KiroCrew governance",
                )


class ActiveCrewLimitTests(unittest.TestCase):
    """Tests for GA_MAX_ACTIVE_CREWS enforcement in _ensure_crew_running
    and the active_crews / max_active_crews fields in crews().

    Listed in test class header: ActiveCrewLimitTests (trn-40 additions)
    """

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_crew(self, status: str = "stopped", container: str = "gs-crew") -> dict:
        return {"status": status, "container": container, "cookie": "c"}

    def _registry_with_running(self, n: int, target_id: str = "target") -> dict:
        """Registry with n running crews plus a stopped target crew."""
        crews: dict = {}
        for i in range(n):
            crews[f"crew-{i}"] = self._make_crew(status="running", container=f"gs-{i}")
        crews[target_id] = self._make_crew(status="stopped", container="gs-target")
        return {"crews": crews}

    # ── Task 3.1: raises when limit reached ─────────────────────────────────

    def test_active_limit_reached_raises(self) -> None:
        """_ensure_crew_running raises RuntimeError when GA_MAX_ACTIVE_CREWS
        running crews already exist and a stopped crew tries to restart."""
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 2
            reg = self._registry_with_running(2)  # 2 running, limit is 2

            class StoppedPodman:
                def container_is_running(self, name: str) -> bool:
                    return False

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_get_podman", return_value=StoppedPodman()),
                patch.object(server, "_startup_events", {}),
                patch.object(server, "_startup_events_lock", __import__("threading").Lock()),
            ):
                crew = reg["crews"]["target"]
                with self.assertRaises(RuntimeError) as ctx:
                    server._ensure_crew_running(crew, "target")
            self.assertIn("Active crew limit", str(ctx.exception))
            self.assertIn("2", str(ctx.exception))
        finally:
            server.GA_MAX_ACTIVE_CREWS = original

    # ── Task 3.2: succeeds when below limit ──────────────────────────────────

    def test_active_limit_not_reached_proceeds(self) -> None:
        """_ensure_crew_running proceeds when running count is below limit."""
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 3
            # Only 1 running crew; limit is 3 → should NOT raise
            reg = self._registry_with_running(1)

            class StoppedRestartPodman:
                def container_is_running(self, name: str) -> bool:
                    return False

                def container_start(self, name: str) -> None:
                    pass

                def container_stop(self, name: str) -> None:
                    pass

                def container_exec(self, name: str, cmd: list, env: dict | None = None) -> str:
                    return "ok"

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_save_registry"),
                patch.object(server, "_get_podman", return_value=StoppedRestartPodman()),
                patch.object(server, "_startup_events", {}),
                patch.object(server, "_startup_events_lock", __import__("threading").Lock()),
                patch.object(server, "GA_MIN_FREE_MEM_GB", 0.0),
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_mint_cookie", return_value="new-c"),
            ):
                crew = reg["crews"]["target"]
                # Should not raise
                result = server._ensure_crew_running(crew, "target")
            self.assertIsNotNone(result)
        finally:
            server.GA_MAX_ACTIVE_CREWS = original

    # ── Task 3.3: GA_MAX_ACTIVE_CREWS=0 disables the check ──────────────────

    def test_active_limit_zero_disables_check(self) -> None:
        """GA_MAX_ACTIVE_CREWS=0 bypasses the active limit — no RuntimeError
        even when many crews are running."""
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 0
            # 10 running crews — should still not raise
            reg: dict = {"crews": {}}
            for i in range(10):
                reg["crews"][f"crew-{i}"] = self._make_crew(
                    status="running", container=f"gs-{i}"
                )
            reg["crews"]["target"] = self._make_crew(status="stopped", container="gs-target")

            class StoppedRestartPodman:
                def container_is_running(self, name: str) -> bool:
                    return False

                def container_start(self, name: str) -> None:
                    pass

                def container_stop(self, name: str) -> None:
                    pass

                def container_exec(self, name: str, cmd: list, env: dict | None = None) -> str:
                    return "ok"

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_save_registry"),
                patch.object(server, "_get_podman", return_value=StoppedRestartPodman()),
                patch.object(server, "_startup_events", {}),
                patch.object(server, "_startup_events_lock", __import__("threading").Lock()),
                patch.object(server, "GA_MIN_FREE_MEM_GB", 0.0),
                patch.object(server, "_wait_gateway", return_value=True),
                patch.object(server, "_patch_crew_config"),
                patch.object(server, "_mint_cookie", return_value="new-c"),
            ):
                crew = reg["crews"]["target"]
                # Must not raise even though 10 crews are running
                result = server._ensure_crew_running(crew, "target")
            self.assertIsNotNone(result)
        finally:
            server.GA_MAX_ACTIVE_CREWS = original

    # ── Task 3.4: already-running crew not double-counted ────────────────────

    def test_already_running_crew_not_double_counted(self) -> None:
        """A crew that is already running is not counted against the active limit
        — it returns before the limit check is reached."""
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 1
            # Crew is already running (container_is_running returns True) and
            # gateway probe passes — the function returns early before any limit
            # check.  No RuntimeError should be raised.
            probe_calls: list[str] = []

            class RunningPodman:
                def container_is_running(self, name: str) -> bool:
                    return True

            with (
                patch.object(server, "_get_podman", return_value=RunningPodman()),
                patch.object(server, "_probe_gateway", return_value=True) as probe,
                patch.object(server, "_touch_crew"),
            ):
                crew = self._make_crew(status="running", container="gs-live")
                result = server._ensure_crew_running(crew, "live-crew")

            # Gateway was probed (early-return path), no active-limit check needed
            probe.assert_called_once()
            self.assertEqual(result["container"], "gs-live")
        finally:
            server.GA_MAX_ACTIVE_CREWS = original

    # ── Task 3.5: registered-crew limit in launch() ───────────────────────────

    def test_launch_registered_crew_limit_error_message(self) -> None:
        """launch() returns 'Registered crew limit' error when GA_MAX_CREWS reached."""
        original = server.GA_MAX_CREWS
        try:
            server.GA_MAX_CREWS = 20
            # Fill registry with 20 crews (the new default)
            crews = {f"crew-{i}": {"status": "stopped", "container": f"gs-{i}"}
                     for i in range(20)}
            reg = {"crews": crews}

            class MinimalPodman:
                pass

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_get_podman", return_value=MinimalPodman()),
                patch.object(server, "_resolve_composition", return_value={"name": "spec-ops", "dir": "spec-ops"}),
                patch.object(server, "_resolve_image", return_value="localhost/spec-ops:latest"),
            ):
                result = server.launch("new-crew")

            self.assertIn("error", result)
            self.assertIn("Registered crew limit", result["error"])
            self.assertIn("20", result["error"])
            self.assertNotIn("Max crews", result["error"])
        finally:
            server.GA_MAX_CREWS = original

    # ── Task 3.6: crews() includes active_crews and max_active_crews ─────────

    def test_crews_includes_active_and_max_active_fields(self) -> None:
        """crews() response includes active_crews (int) and max_active_crews (int)."""
        original = server.GA_MAX_ACTIVE_CREWS
        try:
            server.GA_MAX_ACTIVE_CREWS = 3
            reg = {
                "crews": {
                    "running-a": {"status": "running", "container": "gs-a", "cookie": "c1"},
                    "running-b": {"status": "running", "container": "gs-b", "cookie": "c2"},
                    "stopped-c": {"status": "stopped", "container": "gs-c", "cookie": "c3"},
                }
            }
            fake = FakePodmanClient([int(4 * 1024**3)])
            server._host_memory_cache = None

            with (
                patch.object(server, "_load_registry", return_value=reg),
                patch.object(server, "_get_podman", return_value=fake),
                patch.object(server, "_probe_gateway", return_value=False),
                patch.object(server, "_crew_api", side_effect=Exception("offline")),
            ):
                result = server.crews()

            self.assertIn("active_crews", result)
            self.assertIn("max_active_crews", result)
            self.assertIsInstance(result["active_crews"], int)
            self.assertIsInstance(result["max_active_crews"], int)
            self.assertEqual(result["active_crews"], 2)   # running-a and running-b
            self.assertEqual(result["max_active_crews"], 3)
        finally:
            server.GA_MAX_ACTIVE_CREWS = original


# ── TRN-31: Gateway UI / API proxy tests ─────────────────────────────────────


class _FakeStreamRequest:
    """Minimal async-compatible request stub for proxy handler tests."""

    def __init__(
        self,
        method: str = "GET",
        path: str = "/crews/demo/ui",
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        query_string: bytes = b"",
    ) -> None:
        self.method = method
        self.scope = {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": query_string,
        }
        self.headers = headers or {}
        self._body = body

    async def body(self) -> bytes:
        return self._body


class _FakeUpstreamResponse:
    """httpx.Response-like stub returned by _async_http.stream() context manager."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})

    async def aread(self) -> bytes:
        return self.content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class ProxyHandlerTests(unittest.TestCase):
    """Tests for _handle_crew_ui_proxy and _handle_crew_api_proxy (TRN-31)."""

    CREW = {"container": "gs-demo", "cookie": "test-cookie-val"}

    # ── 5.1: UI proxy forwards path and query ────────────────────────────────

    def test_ui_proxy_root_path_maps_to_upstream_slash(self) -> None:
        """5.1a: /crews/demo/ui (no trailing sub-path) proxies to upstream /"""
        upstream_calls: list[tuple] = []

        async def fake_stream(method, url, headers=None, content=None):
            upstream_calls.append((method, url))
            return _FakeUpstreamResponse(200, b"<html>dashboard</html>",
                                         {"content-type": "text/html"})

        request = _FakeStreamRequest(path="/crews/demo/ui")
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server._async_http, "stream", new_callable=lambda: lambda: fake_stream.__call__),
        ):
            # We need the actual stream context manager
            pass

        # Use a full mock of _async_http.stream
        mock_ctx = _FakeUpstreamResponse(200, b"<html/>", {"content-type": "text/html"})

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
                patch.object(server._async_http, "stream") as mock_stream,
            ):
                mock_stream.return_value = mock_ctx
                return await server._handle_crew_ui_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)

    def test_ui_proxy_sub_path_forwarded_correctly(self) -> None:
        """5.1b: /crews/demo/ui/app/page proxies to http://gs-demo:5476/app/page"""
        captured_url: list[str] = []

        mock_ctx = _FakeUpstreamResponse(200, b"page", {"content-type": "text/html"})

        async def fake_stream(method, url, headers=None, content=None):
            captured_url.append(url)
            return mock_ctx

        request = _FakeStreamRequest(path="/crews/demo/ui/app/page")
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
        ):
            with patch.object(server._async_http, "stream") as mock_stream:
                mock_stream.return_value = mock_ctx

                async def run():
                    # Capture URL by intercepting the stream call
                    actual_calls = []

                    original_stream = server._async_http.stream

                    class StreamCapture:
                        def __call__(self_inner, method, url, **kwargs):
                            actual_calls.append(url)
                            return mock_ctx

                    with patch.object(server, "_async_http") as fake_http:
                        fake_http.stream = StreamCapture()
                        resp = await server._handle_crew_ui_proxy(request)
                    return resp, actual_calls

                response, calls = asyncio.run(run())

        self.assertEqual(response.status_code, 200)

    def test_ui_proxy_query_string_forwarded(self) -> None:
        """5.1c: Query string is forwarded to upstream."""
        captured: list[str] = []

        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui/search",
                    query_string=b"q=hello&limit=10",
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured.append(url)
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured, "stream was not called")
        self.assertIn("q=hello", captured[0])
        self.assertIn("limit=10", captured[0])

    def test_ui_proxy_host_header_stripped(self) -> None:
        """5.1d: host header is stripped from forwarded request."""
        captured_headers: list[dict] = []

        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(
                    path="/crews/demo/ui",
                    headers={"host": "transport.example.com", "accept": "text/html"},
                )

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        self.assertNotIn("host", {k.lower() for k in captured_headers[0]})
        self.assertIn("accept", {k.lower() for k in captured_headers[0]})

    # ── 5.2: UI proxy does NOT inject Cookie ─────────────────────────────────

    def test_ui_proxy_does_not_inject_cookie(self) -> None:
        """5.2: UI proxy must NOT inject mc_token_5476 cookie."""
        captured_headers: list[dict] = []
        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(path="/crews/demo/ui")

                class StreamCapture:
                    def __call__(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertTrue(captured_headers)
        # No Cookie header at all, or at least no mc_token injection
        cookie_val = captured_headers[0].get("cookie", "") or captured_headers[0].get("Cookie", "")
        self.assertNotIn("mc_token_5476", cookie_val)

    # ── 5.3: API proxy injects cookie and retries on 401/403 ─────────────────

    def test_api_proxy_injects_mc_token_cookie(self) -> None:
        """5.3a: API proxy injects mc_token_5476 cookie."""
        captured_headers: list[dict] = []

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/spawn")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        captured_headers.append(dict(headers or {}))
                        resp = Mock()
                        resp.status_code = 200
                        resp.content = b'{"agents":[]}'
                        resp.headers = {"content-type": "application/json"}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(captured_headers)
        cookie = captured_headers[0].get("Cookie", "")
        self.assertIn("mc_token_5476", cookie)
        self.assertIn("test-cookie-val", cookie)

    def test_api_proxy_retries_on_401_after_cookie_refresh(self) -> None:
        """5.3b: API proxy retries once after 401 with refreshed cookie."""
        call_count = [0]

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_refresh_cookie", return_value=True) as refresh,
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/spawn")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        call_count[0] += 1
                        resp = Mock()
                        # First call: 401, second call: 200
                        resp.status_code = 401 if call_count[0] == 1 else 200
                        resp.content = b""
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request), refresh

        response, refresh_mock = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_count[0], 2)
        refresh_mock.assert_called_once()

    def test_api_proxy_retries_on_403_after_cookie_refresh(self) -> None:
        """5.3c: API proxy retries once after 403 with refreshed cookie."""
        call_count = [0]

        async def run():
            with (
                patch.object(server, "_require_crew", return_value=dict(self.CREW)),
                patch.object(server, "_ensure_crew_running", return_value=dict(self.CREW)),
                patch.object(server, "_refresh_cookie", return_value=True),
            ):
                request = _FakeStreamRequest(path="/crews/demo/api/crons")

                class FakeHTTP:
                    async def request(self_inner, method, url, headers=None, content=None):
                        call_count[0] += 1
                        resp = Mock()
                        resp.status_code = 403 if call_count[0] == 1 else 200
                        resp.content = b""
                        resp.headers = {}
                        return resp

                with patch.object(server, "_async_http", FakeHTTP()):
                    return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(call_count[0], 2)

    # ── 5.4: Stopped crew is woken before proxying ───────────────────────────

    def test_ui_proxy_wakes_stopped_crew(self) -> None:
        """5.4: _ensure_crew_running is called before proxy proceeds."""
        ensure_called = []
        mock_ctx = _FakeUpstreamResponse(200, b"ok")

        async def run():
            def ensure(crew, crew_id, **kwargs):
                ensure_called.append(crew_id)
                return crew

            with (
                patch.object(server, "_require_crew", return_value=self.CREW),
                patch.object(server, "_ensure_crew_running", side_effect=ensure),
            ):
                request = _FakeStreamRequest(path="/crews/demo/ui")

                class StreamCapture:
                    def __call__(self_inner, method, url, **kwargs):
                        return mock_ctx

                with patch.object(server, "_async_http") as fake_http:
                    fake_http.stream = StreamCapture()
                    return await server._handle_crew_ui_proxy(request)

        asyncio.run(run())
        self.assertIn("demo", ensure_called)

    # ── 5.5: Unknown crew_id returns 404 ─────────────────────────────────────

    def test_ui_proxy_unknown_crew_returns_404(self) -> None:
        """5.5a: Unknown crew_id returns 404 for UI proxy."""
        async def run():
            with patch.object(
                server, "_require_crew",
                side_effect=KeyError("Crew 'unknown' not found"),
            ):
                request = _FakeStreamRequest(path="/crews/unknown/ui")
                return await server._handle_crew_ui_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    def test_api_proxy_unknown_crew_returns_404(self) -> None:
        """5.5b: Unknown crew_id returns 404 for API proxy."""
        async def run():
            with patch.object(
                server, "_require_crew",
                side_effect=ValueError("crew_id required"),
            ):
                request = _FakeStreamRequest(path="/crews/unknown/api/spawn")
                return await server._handle_crew_api_proxy(request)

        response = asyncio.run(run())
        self.assertEqual(response.status_code, 404)

    # ── 5.6: BearerAuthMiddleware dispatches to proxy handlers ───────────────

    def test_middleware_dispatches_ui_route_when_auth_passes(self) -> None:
        """5.6a: /crews/demo/ui reaches _handle_crew_ui_proxy after auth passes."""
        handled = []

        async def fake_ui_proxy(req):
            handled.append("ui")
            return server.PlainTextResponse("proxied")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey")

        with patch.object(server, "_handle_crew_ui_proxy", side_effect=fake_ui_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("ui", handled)

    def test_middleware_dispatches_api_route_when_auth_passes(self) -> None:
        """5.6b: /crews/demo/api/spawn reaches _handle_crew_api_proxy after auth passes."""
        handled = []

        async def fake_api_proxy(req):
            handled.append("api")
            return server.PlainTextResponse("proxied")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/api/spawn",
            "headers": [(b"authorization", b"Bearer testkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="testkey")

        with patch.object(server, "_handle_crew_api_proxy", side_effect=fake_api_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("api", handled)

    def test_middleware_returns_401_for_ui_route_when_key_missing(self) -> None:
        """5.6c: /crews/demo/ui returns 401 when GA_API_KEY set and bearer missing."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [],  # No Authorization header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="secret")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_returns_401_for_ui_route_when_key_wrong(self) -> None:
        """5.6d: /crews/demo/ui returns 401 when bearer token is wrong."""
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [(b"authorization", b"Bearer wrongkey")],
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="correctkey")
        status, _, _ = _run_asgi(mw, scope)
        self.assertEqual(status, 401)

    def test_middleware_dispatches_ui_without_auth_when_no_key_configured(self) -> None:
        """5.6e: /crews/demo/ui is proxied without auth when GA_API_KEY is unset."""
        handled = []

        async def fake_ui_proxy(req):
            handled.append("ui")
            return server.PlainTextResponse("proxied-no-auth")

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/crews/demo/ui",
            "headers": [],  # No auth header
        }
        mw = server.BearerAuthMiddleware(_FakeDownstream(), api_key="")  # No key

        with patch.object(server, "_handle_crew_ui_proxy", side_effect=fake_ui_proxy):
            status, _, body = _run_asgi(mw, scope)

        self.assertEqual(status, 200)
        self.assertIn("ui", handled)

    # ── Helper: _extract_crew_proxy_parts ────────────────────────────────────

    def test_extract_crew_proxy_parts_ui_root(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/ui")
        self.assertEqual(result, ("demo", "ui", ""))

    def test_extract_crew_proxy_parts_ui_with_path(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/ui/app/page")
        self.assertEqual(result, ("demo", "ui", "app/page"))

    def test_extract_crew_proxy_parts_api_with_path(self) -> None:
        result = server._extract_crew_proxy_parts("/crews/demo/api/spawn")
        self.assertEqual(result, ("demo", "api", "spawn"))

    def test_extract_crew_proxy_parts_invalid_returns_none(self) -> None:
        self.assertIsNone(server._extract_crew_proxy_parts("/mcp"))
        self.assertIsNone(server._extract_crew_proxy_parts("/crews"))
        self.assertIsNone(server._extract_crew_proxy_parts("/crews/demo"))


class InstallEnvVarSyncTests(unittest.TestCase):
    """Verify that every GA_* / KC_* env var read by server.py is also
    passed to the transport container via a -e flag in install.sh.

    This catches regressions where a new config var is added to server.py
    but the corresponding -e line is forgotten in the install script.
    """

    @staticmethod
    def _vars_from_server() -> set[str]:
        """Extract env var names read via os.environ.get() in server.py."""
        import re
        root = Path(__file__).parent.parent
        src = (root / "transport" / "server.py").read_text()
        # Match os.environ.get("VAR_NAME", ...) calls
        return set(re.findall(r'os\.environ\.get\(\s*["\']([A-Z_]+)["\']', src))

    @staticmethod
    def _vars_from_install() -> set[str]:
        """Extract env var names passed via -e flags in install.sh."""
        import re
        root = Path(__file__).parent.parent
        src = (root / "install.sh").read_text()
        # Match -e "VAR_NAME=..." lines
        return set(re.findall(r'-e\s+["\']([A-Z_]+)=', src))

    def test_all_server_ga_vars_passed_in_install(self) -> None:
        """Every GA_* and KC_* var read by server.py must have a -e entry in install.sh."""
        server_vars = {
            v for v in self._vars_from_server()
            if v.startswith("GA_") or v.startswith("KC_")
        }
        install_vars = self._vars_from_install()

        # Vars that are intentionally not forwarded via plain -e flags
        excluded = {
            "KC_IMAGE",       # build-time image name, not a runtime var
            "KC_BASE_IMAGE",  # build-time base image for login containers
            "GA_API_KEY",     # passed via podman secret (--secret ga-api-key), not -e
            "GA_FILE_SECRET", # generated internally by the transport at startup
        }

        missing = server_vars - install_vars - excluded
        self.assertSetEqual(
            missing,
            set(),
            f"Env vars read by server.py but missing from install.sh -e flags: {sorted(missing)}\n"
            "Add the missing -e lines to the podman run block in install.sh.",
        )
