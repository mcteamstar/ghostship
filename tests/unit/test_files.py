"""Unit tests for ``transport.files`` — file/bundle signing + transfer handlers.

TRN-85: migration target for classes whose function-under-test is defined in
``files.py`` (``_sign_file_url``, ``_sign_upload_url``, ``_verify_file_token``,
``_handle_file_get``, ``_handle_file_put``, ``_transfer_upload``,
``_TarMemberStream``, ``_ResponseChunkReader``) and the ``evac``/``supply``
MCP transfer tools. Patch via ``transport.files`` for the owning-module
functions; patch ``server.<tool>`` at the call site for the MCP tools.

Some classes here are podman/git-gated with
``@unittest.skipUnless(shutil.which(\"git\"), ...)`` and auto-skip when the
binary is absent.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from tests.unit.helpers import Request, files_mod, lifecycle, server  # noqa: F401


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


class MalformedBundleGetPodman(BundleGetPodman):
    def container_archive_get(self, container: str, path: str) -> BundleArchiveResponse:
        self.archive_calls.append((container, path))
        return BundleArchiveResponse(b"not a tar stream")


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
            patch.object(files_mod, "KIRO_WORKSPACE_ROOT", str(workspace)),
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(files_mod, "_get_podman", return_value=podman),
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
            patch.object(files_mod, "KIRO_WORKSPACE_ROOT", str(workspace)),
            patch.object(lifecycle, "_require_crew", return_value=crew),
            patch.object(lifecycle, "_ensure_crew_running", return_value=crew),
            patch.object(files_mod, "_get_podman", return_value=podman),
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
            server._verify_file_token("demo", "repo", query["expires"], query["sig"], mode="")
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
    """GA_HOST_URL > localhost default."""

    def _url_base(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"

    def test_sign_file_url_uses_ga_public_url_when_set(self) -> None:
        # TRN-75: GA_HOST_URL is read once at startup into cfg.ga_host_url;
        # patch the resolved config field rather than os.environ.
        # TRN-71: _resolve_public_url_base moved to transport.files — patch its cfg.
        with patch.object(files_mod.cfg, "ga_host_url", "https://academy.example.com"):
            url = server._sign_file_url("demo", "repo")
        self.assertTrue(url.startswith("https://academy.example.com/"), url)

    def test_sign_file_url_uses_localhost_default_when_unset(self) -> None:
        with patch.object(files_mod.cfg, "ga_host_url", ""):
            url = server._sign_file_url("demo", "repo")
        self.assertIn("localhost", url, url)

    def test_sign_upload_url_uses_ga_public_url_when_set(self) -> None:
        with patch.object(files_mod.cfg, "ga_host_url", "https://academy.example.com"):
            url = server._sign_upload_url("demo", "repo")
        self.assertTrue(url.startswith("https://academy.example.com/"), url)

    def test_evac_presigned_url_uses_ga_public_url_base(self) -> None:
        with patch.object(files_mod.cfg, "ga_host_url", "https://cdn.example.com"):
            url = server._sign_file_url("crew1", "workspace/bundle.tar")
        self.assertEqual(self._url_base(url), "https://cdn.example.com")
        self.assertIn("/files/crew1/workspace/bundle.tar", url)


if __name__ == "__main__":
    unittest.main()
