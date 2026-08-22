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
        sign.assert_called_once_with("demo", "repo")


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
    """GA_FILE_PUBLIC_URL > GA_PUBLIC_URL > localhost default (task 1.8 / srv-67)."""

    def _url_base(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def test_sign_file_url_uses_ga_file_public_url_when_set(self) -> None:
        env = {"GA_FILE_PUBLIC_URL": "https://files.example.com"}
        with patch.dict(os.environ, env, clear=False):
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("https://files.example.com/"), url)

    def test_sign_file_url_falls_back_to_ga_public_url(self) -> None:
        env = {"GA_PUBLIC_URL": "http://fallback:8001"}
        with patch.dict(os.environ, env, clear=False):
            # Ensure GA_FILE_PUBLIC_URL is absent
            os.environ.pop("GA_FILE_PUBLIC_URL", None)
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("http://fallback:8001/"), url)

    def test_sign_file_url_uses_localhost_default_when_both_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GA_FILE_PUBLIC_URL", None)
            os.environ.pop("GA_PUBLIC_URL", None)
            url = server._sign_file_url("demo", "repo")
        self.assertIn("localhost", url, url)

    def test_sign_file_url_ga_file_public_url_wins_over_ga_public_url(self) -> None:
        env = {
            "GA_FILE_PUBLIC_URL": "https://files.example.com",
            "GA_PUBLIC_URL": "http://fallback:8001",
        }
        with patch.dict(os.environ, env, clear=False):
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("https://files.example.com/"), url)

    def test_sign_upload_url_uses_ga_file_public_url_when_set(self) -> None:
        env = {"GA_FILE_PUBLIC_URL": "https://files.example.com"}
        with patch.dict(os.environ, env, clear=False):
            url = server._sign_upload_url("demo", "repo")
        self.assertTrue(url.startswith("https://files.example.com/"), url)

    def test_sign_upload_url_falls_back_to_ga_public_url(self) -> None:
        env = {"GA_PUBLIC_URL": "http://fallback:8001"}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("GA_FILE_PUBLIC_URL", None)
            url = server._sign_upload_url("demo", "repo")
        self.assertTrue(url.startswith("http://fallback:8001/"), url)

    def test_sign_upload_url_ga_file_public_url_wins_over_ga_public_url(self) -> None:
        env = {
            "GA_FILE_PUBLIC_URL": "https://files.example.com",
            "GA_PUBLIC_URL": "http://fallback:8001",
        }
        with patch.dict(os.environ, env, clear=False):
            url = server._sign_upload_url("demo", "repo")
        self.assertTrue(url.startswith("https://files.example.com/"), url)


class LifecycleRegressionTests(unittest.TestCase):
    def test_supply_recovers_before_signing_upload_url(self) -> None:
        events: list[str] = []
        crew = {"container": "gs-demo", "cookie": "old"}

        def ensure(value: dict, crew_id: str) -> dict:
            events.append("ensure")
            return value

        def sign(crew_id: str, path: str) -> str:
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
            patch.object(server.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(server.time, "sleep", side_effect=advance),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=5)

        self.assertFalse(result["done"])
        self.assertEqual(result["crew_id"], "demo")
        # Should not have "error" key set (or empty string)
        self.assertNotIn("reason", result)
        self.assertFalse(result.get("error"))

    def test_pickup_mail_counts_present_single_task(self) -> None:
        """5.4 — mail counts present in single-task response."""
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value=self._task_response(True, agent="ghost")),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 3, "admiral": 1}),
        ):
            result = server.pickup(task_id="task-1", crew_id="demo", timeout_secs=0)

        self.assertEqual(result["agent_mail"], 3)
        self.assertEqual(result["admiral_mail"], 1)

    def test_pickup_mail_counts_present_list_all(self) -> None:
        """5.4 — mail counts present in list-all response."""
        agents = [{"id": "a", "done": True, "task": "t1", "agent": "ghost", "elapsed": 5}]

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api", return_value={"agents": agents}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_all_mail_counts", return_value={"ghost": 2, "admiral": 1}),
        ):
            result = server.pickup(crew_id="demo", timeout_secs=0)

        self.assertIn("mail_summary", result)
        self.assertEqual(result["mail_summary"]["ghost"], 2)
        self.assertEqual(result["admiral_mail"], 1)

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
        rejected = ("kirocrew", "kirocrew-default", "custom-agent", "unknown")
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
        append.assert_called_once_with(podman, "gs-demo", expected)
        self.assertIn("demo-change", append.call_args.args[2])
        self.assertNotIn("<change>", append.call_args.args[2])
        self.assertEqual(api.call_args_list[1].args[:3], (self.CREW, "POST", "/api/crons"))
        self.assertEqual(api.call_args_list[1].kwargs["json"]["agent"], "raven")
        # Immediate dispatch should have been called (interval → fire_immediately defaults True)
        self.assertEqual(api.call_args_list[2].args[:3], (self.CREW, "POST", "/api/spawn"))

    def test_order_appends_mail_after_checkin_is_ready(self) -> None:
        podman = Mock()
        events: list[str] = []

        def append(_podman: Any, _container: str, _body: str) -> None:
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
        definition = server._ORDER_TEMPLATES["sdd"]

        self.assertIn("## sdd", resource)
        self.assertIn(definition["description"], resource)
        self.assertIn(definition["body"], resource)
        self.assertIn("openspec store list --json", definition["body"])
        self.assertIn("openspec store register", definition["body"])
        self.assertIn("`--store <id>`", definition["body"])
        self.assertIn("fix findings that fit this change", definition["body"])
        self.assertIn("kirocrew", definition["body"])
        self.assertIn("spawn list", definition["body"])
        self.assertIn("cron list", definition["body"])
        self.assertIn("cron pause", definition["body"])
        self.assertIn("cron resume", definition["body"])
        self.assertIn("/home/kirocrew/.kiro/crew/.local_secret", definition["body"])
        self.assertIn("X-Internal-Secret", definition["body"])
        self.assertIn("localhost:5476", definition["body"])
        self.assertIn("/api/spawn", definition["body"])
        self.assertIn("/api/spawn/{task_id}", definition["body"])
        self.assertIn("/api/spawn/{task_id}/steer", definition["body"])
        self.assertIn("/api/spawn/{task_id}/continue", definition["body"])
        self.assertIn('"mode": "follow_up"', definition["body"])
        self.assertIn("pause your own check-in job", definition["body"])
        self.assertIn("the only one in this crew", definition["body"])
        self.assertIn("never let its value show up anywhere", definition["body"])
        self.assertNotIn("captain-check-in", definition["body"])
        self.assertNotIn("external `captain(..., action=\"stop\")` operation", definition["body"])

    def test_raven_prompt_covers_gateway_status_and_self_cancellation(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]

        for phrase in (
            "kirocrew",
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
            "pause your own check-in job",
            "the only one in this crew",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prompt)
        self.assertNotIn("captain-check-in", prompt)
        self.assertNotIn("native worker-status tool is not exposed", prompt)
        self.assertNotIn("agent shells do not receive", prompt)
        self.assertNotIn("native in-session spawn tooling", prompt)

    def test_raven_and_sdd_bodies_cover_running_task_steering(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]
        bodies = {"raven prompt": prompt, "sdd template": server._ORDER_TEMPLATES["sdd"]["body"]}
        for label, body in bodies.items():
            with self.subTest(body=label):
                for phrase in (
                    "steer it with the new context rather than waiting for it to finish",
                    "/api/spawn/{task_id}/steer",
                    "/api/spawn/{task_id}/continue",
                    '"mode": "follow_up"',
                ):
                    self.assertIn(phrase, body)
                self.assertNotIn("native in-session spawn tooling", body)

    def test_raven_and_sdd_bodies_cover_persona_mailbox_skim(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]
        bodies = {"raven prompt": prompt, "sdd template": server._ORDER_TEMPLATES["sdd"]["body"]}
        for label, body in bodies.items():
            with self.subTest(body=label):
                for persona in ("ghost", "spectre", "banshee", "wraith", "reaper"):
                    self.assertIn(f"/var/mail/{persona}", body)
                self.assertIn("never marks anything as read", body)
                self.assertIn("spawn list", body)

    def test_raven_and_sdd_bodies_cover_full_store_registration_command(self) -> None:
        definition_path = Path(__file__).resolve().parents[1] / "academy" / "agents" / "raven.json"
        prompt = json.loads(definition_path.read_text())["prompt"]
        bodies = {"raven prompt": prompt, "sdd template": server._ORDER_TEMPLATES["sdd"]["body"]}
        for label, body in bodies.items():
            with self.subTest(body=label):
                self.assertIn("openspec store list --json", body)
                self.assertIn("openspec store register", body)
                self.assertIn("--id repo", body)
                self.assertIn("--yes", body)
                self.assertIn("PROJECT_ROOT", body)
                self.assertIn("subagent_*", body)
                self.assertIn("--store <id>", body)

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
            podman, "gs-demo", "implement the objective"
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
        append.assert_called_once_with(podman, "gs-demo", "new order")
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

    def test_mail_helper_matches_radio_format_and_escapes_from_lines(self) -> None:
        message = server._format_captain_mail("first order\nsecond line")
        lines = message.split("\n")
        self.assertTrue(lines[0].startswith("From admiral@localhost "))
        self.assertEqual(lines[1], "From: admiral@localhost")
        self.assertEqual(lines[2], "To: captain@localhost")
        self.assertEqual(lines[3], "Subject: Standing order")
        self.assertTrue(lines[4].startswith("Date: "))
        self.assertEqual(lines[5], "")
        self.assertTrue(message.endswith("first order\nsecond line\n\n"))
        escaped = server._format_captain_mail("safe\nFrom corrupt boundary")
        self.assertTrue(escaped.endswith("safe\n>From corrupt boundary\n\n"))

        podman = Mock()
        server._append_captain_mail(podman, "gs-demo", "first order")
        command = podman.container_exec_checked.call_args.args[1]
        self.assertEqual(command[:2], ["python3", "-c"])
        self.assertIn("/var/mail/captain", command[2])
        self.assertIn("os.O_APPEND", command[2])

    def test_mail_append_does_not_chmod_shared_mail_directory(self) -> None:
        podman = Mock()
        server._append_captain_mail(podman, "gs-demo", "first order")
        script = podman.container_exec_checked.call_args.args[1][2]
        self.assertNotIn("os.chmod(path.parent", script)
        self.assertIn("os.fchmod(fd, 0o600)", script)
        self.assertIn("os.chmod(path, 0o600)", script)

    def test_mail_count_only_ignores_a_missing_mailbox(self) -> None:
        missing = Mock()
        missing.container_exec_checked.return_value = server._MBOX_MISSING_MARKER + "\n"
        self.assertEqual(server._mail_count(missing, "gs-demo", "/var/mail/captain"), 0)
        script = missing.container_exec_checked.call_args.args[1][2]
        self.assertIn('[ -f "/var/mail/captain" ]', script)
        self.assertNotIn("no such file", script.lower())

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
        append.assert_called_once_with(podman, "gs-demo", "resume this")
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
                {"name": "kirocrew", "description": "Default type", "dir": "kirocrew"},
                {"name": "custom", "description": "Custom type", "dir": "custom", "image": "custom:latest"},
            ]
        })
        with tempfile.TemporaryDirectory() as tmp:
            registry_path = Path(tmp) / "registry.json"
            registry_path.write_text(registry_data)
            crews_dir = Path(tmp) / "kirocrew"
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
            kirocrew_dir = Path(tmp).parent / "crews" / "kirocrew"
            custom_dir2 = Path(tmp).parent / "crews" / "custom"

            # We test by patching the path and directory checks
            with patch.object(server, "_CREW_REGISTRY_PATH", reg_path):
                with patch("pathlib.Path.is_dir", return_value=True):
                    result = server._load_composition_registry()

        self.assertIn("kirocrew", result)
        self.assertIn("custom", result)
        self.assertEqual(result["kirocrew"]["dir"], "kirocrew")
        self.assertEqual(result["custom"]["image"], "custom:latest")

    def test_missing_file_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback when file is missing."""
        with patch.object(server, "_CREW_REGISTRY_PATH", Path("/nonexistent/registry.json")):
            result = server._load_composition_registry()

        self.assertEqual(list(result.keys()), ["kirocrew"])
        self.assertEqual(result["kirocrew"]["dir"], "kirocrew")

    def test_malformed_json_returns_fallback(self) -> None:
        """_load_composition_registry() returns fallback for malformed JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json!!!")
            f.flush()
            try:
                with patch.object(server, "_CREW_REGISTRY_PATH", Path(f.name)):
                    result = server._load_composition_registry()
                self.assertEqual(list(result.keys()), ["kirocrew"])
            finally:
                Path(f.name).unlink()

    def test_invalid_entries_excluded(self) -> None:
        """_load_composition_registry() skips entries with invalid names."""
        registry_data = json.dumps({
            "compositions": [
                {"name": "INVALID-CAPS", "description": "Bad", "dir": "caps"},
                {"name": "kirocrew", "description": "Good", "dir": "kirocrew"},
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
                self.assertIn("kirocrew", result)
            finally:
                Path(f.name).unlink()


class TestCrewTypeHelpers(unittest.TestCase):
    """Unit tests for _resolve_manifest_path and _resolve_image."""

    def test_resolve_manifest_path(self) -> None:
        entry = {"name": "kirocrew", "dir": "kirocrew"}
        self.assertEqual(server._resolve_manifest_path(entry), Path("/crews/kirocrew/manifest.json"))

    def test_resolve_manifest_path_custom_dir(self) -> None:
        entry = {"name": "custom", "dir": "my-custom-crew"}
        self.assertEqual(server._resolve_manifest_path(entry), Path("/crews/my-custom-crew/manifest.json"))

    def test_resolve_image_with_override(self) -> None:
        entry = {"name": "custom", "dir": "custom", "image": "custom:v2"}
        self.assertEqual(server._resolve_image(entry), "custom:v2")

    def test_resolve_image_without_override(self) -> None:
        entry = {"name": "kirocrew", "dir": "kirocrew"}
        self.assertEqual(server._resolve_image(entry), server.KC_IMAGE)

    def test_resolve_image_empty_string_uses_default(self) -> None:
        entry = {"name": "kirocrew", "dir": "kirocrew", "image": ""}
        self.assertEqual(server._resolve_image(entry), server.KC_IMAGE)


class TestLaunchCrewType(unittest.TestCase):
    """Integration tests for launch() with composition parameter."""

    def test_launch_with_explicit_composition(self) -> None:
        """launch() with a valid composition resolves image and manifest correctly."""
        test_entry = {"name": "kirocrew", "dir": "kirocrew", "description": "Default"}
        with (
            patch.object(server, "COMPOSITION_REGISTRY", {"kirocrew": test_entry}),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
            patch.object(server, "_finish_crew_setup", return_value={"status": "ready"}) as mock_setup,
            patch.object(server, "_wait_gateway", return_value=True),
        ):
            mock_podman = server._get_podman.return_value
            mock_podman.network_create = Mock()
            mock_podman.volume_create = Mock()
            mock_podman.container_create = Mock()
            mock_podman.container_start = Mock()

            result = server.launch("test-crew", composition="kirocrew")

        self.assertEqual(result["status"], "ready")
        # Verify _finish_crew_setup was called with composition and entry
        call_args = mock_setup.call_args
        self.assertEqual(call_args[0][5], "dGVzdA==")  # auth_b64
        self.assertEqual(call_args[0][6], "kirocrew")  # composition
        self.assertEqual(call_args[0][7], test_entry)  # composition_entry

    def test_launch_with_unknown_composition_errors(self) -> None:
        """launch() with unknown composition returns error listing available types."""
        with (
            patch.object(server, "COMPOSITION_REGISTRY", {"kirocrew": {"name": "kirocrew"}}),
        ):
            result = server.launch("test-crew", composition="nonexistent")

        self.assertIn("error", result)
        self.assertIn("nonexistent", result["error"])
        self.assertIn("kirocrew", result["error"])

    def test_launch_uses_resolved_image_for_container(self) -> None:
        """launch() passes the resolved image to container_create."""
        test_entry = {"name": "custom", "dir": "custom", "description": "Custom", "image": "custom:v3"}
        with (
            patch.object(server, "COMPOSITION_REGISTRY", {"custom": test_entry}),
            patch.object(server, "_get_podman") as mock_get_podman,
            patch.object(server, "_read_auth_file", return_value="dGVzdA=="),
            patch.object(server, "_load_registry", return_value={"crews": {}}),
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
            "kirocrew": {"name": "kirocrew", "dir": "kirocrew", "description": "Default KiroCrew"},
            "custom": {"name": "custom", "dir": "custom", "description": "Custom crew type"},
        }
        with patch.object(server, "COMPOSITION_REGISTRY", test_registry):
            result = server.resource_compositions()

        self.assertIsInstance(result, str)
        self.assertIn("kirocrew", result)
        self.assertIn("custom", result)
        self.assertIn("Default KiroCrew", result)
        self.assertIn("Custom crew type", result)


if __name__ == "__main__":
    unittest.main()
