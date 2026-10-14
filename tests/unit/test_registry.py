"""Unit tests for ``transport.registry`` — crew registry + schedule persistence.

Migration target for classes whose function-under-test is defined in
``registry.py`` (``_load_registry``, ``_save_registry``, ``_get_crew``,
``_touch_crew``, ``_get_crew_schedules``, ``_upsert_crew_schedule``,
``_remove_crew_schedule``, ``_advance_next_fire_at``). Patch via
``transport.registry`` — the call-site principle: these run in registry.py's
namespace even though ``server`` re-exports them.
"""

from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.unit.helpers import registry, server  # noqa: F401


class AdvanceNextFireAtTests(unittest.TestCase):
    """Tests for _advance_next_fire_at."""

    def test_interval_branch(self) -> None:
        """interval_secs=300 advances next_fire_at by ~300 seconds."""
        now = time.time()
        job = {"job_id": "j1", "interval_secs": 300, "cron_expr": None, "one_shot": False}
        registry._advance_next_fire_at(job)
        self.assertAlmostEqual(job["next_fire_at"], now + 300, delta=2.0)

    def test_cron_branch(self) -> None:
        """cron_expr branch matches croniter at a simulated HH:59 time."""
        from datetime import datetime, timezone
        from croniter import croniter

        job = {"job_id": "j2", "interval_secs": None, "cron_expr": "0 * * * *", "one_shot": False}
        now = datetime(2026, 8, 24, 12, 59, 30, tzinfo=timezone.utc).timestamp()
        with patch.object(registry.time, "time", return_value=now):
            registry._advance_next_fire_at(job)

        expected = croniter("0 * * * *", now).get_next(float)
        self.assertEqual(job["next_fire_at"], expected)

    def test_one_shot_branch(self) -> None:
        """one_shot=True sets next_fire_at to _NEVER_FIRE_AT sentinel."""
        job = {"job_id": "j3", "interval_secs": 60, "cron_expr": None, "one_shot": True}
        registry._advance_next_fire_at(job)
        self.assertEqual(job["next_fire_at"], registry._NEVER_FIRE_AT)

    def test_malformed_cron_falls_back_to_60s(self) -> None:
        """Malformed cron expression falls back to +60s (nit 5.3)."""
        now = time.time()
        job = {"job_id": "j4", "interval_secs": None, "cron_expr": "not-a-cron", "one_shot": False}
        with self.assertLogs("transport", level="WARNING") as log_ctx:
            registry._advance_next_fire_at(job)
        self.assertAlmostEqual(job["next_fire_at"], now + 60, delta=2.0)
        self.assertTrue(
            any("croniter failed" in msg and "not-a-cron" in msg for msg in log_ctx.output),
            "Expected warning mentioning 'croniter failed' and the expression",
        )

    def test_unknown_schedule_type_sets_never_fire_at(self) -> None:
        """No interval_secs, no cron_expr, no one_shot → _NEVER_FIRE_AT (nit 5.3)."""
        job = {"job_id": "j5", "interval_secs": None, "cron_expr": None, "one_shot": False}
        registry._advance_next_fire_at(job)
        self.assertEqual(job["next_fire_at"], registry._NEVER_FIRE_AT)


class SaveRegistryDurabilityTests(unittest.TestCase):
    """Tests for _save_registry durability guarantees."""

    def test_fsync_is_called_on_save(self, tmp_path: Path | None = None) -> None:
        """_save_registry calls os.fsync before returning (task 3.1)."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            test_reg = {"crews": {"c1": {"name": "test"}}}
            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch("os.fsync") as mock_fsync,
            ):
                registry._save_registry(test_reg)

            mock_fsync.assert_called()  # called for both file and directory fds
            saved = json.loads(reg_path.read_text())
            self.assertEqual(saved, test_reg)

    def test_tmp_file_created_with_mode_0o600(self) -> None:
        """_save_registry opens .tmp with mode 0o600 (task 3.2)."""
        import tempfile
        captured_modes: list[int] = []
        real_os_open = os.open

        def capturing_os_open(path: str, flags: int, mode: int = 0o777) -> int:
            captured_modes.append((path, mode))
            return real_os_open(path, flags, mode)

        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch("os.open", side_effect=capturing_os_open),
            ):
                registry._save_registry({"crews": {}})

        # Find the call for the .tmp file
        tmp_calls = [(p, m) for (p, m) in captured_modes if p.endswith(".tmp")]
        self.assertTrue(tmp_calls, "Expected os.open to be called for the .tmp file")
        _, mode = tmp_calls[0]
        self.assertEqual(mode, 0o600, f"Expected mode 0o600, got 0o{mode:o}")

    def test_corrupt_json_raises_and_renames_to_corrupt(self) -> None:
        """Corrupt crews.json raises RegistryCorruptError, creates .corrupt,
        removes original."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            corrupt_path = reg_path.with_name(reg_path.name + ".corrupt")
            # Write invalid JSON
            reg_path.write_text("{ this is not json }")
            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                self.assertLogs("transport.registry", level="ERROR") as log_ctx,
            ):
                # _load_registry raises the named
                # RegistryCorruptError instead of re-raising json.JSONDecodeError,
                # giving MCP tool handlers a single exception to catch. The
                # original decode error is preserved as the chained cause.
                with self.assertRaises(registry.RegistryCorruptError) as ctx:
                    registry._load_registry()
                self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)
                # Assertions must be inside the tempfile context so the dir exists
                self.assertTrue(corrupt_path.exists(), "crews.json.corrupt should exist")
                self.assertEqual(
                    corrupt_path.name, "crews.json.corrupt",
                    "Quarantine file must be named crews.json.corrupt per spec",
                )
                self.assertFalse(reg_path.exists(), "crews.json should have been renamed")
            self.assertTrue(
                any("corrupt" in msg.lower() or "parse" in msg.lower() for msg in log_ctx.output),
                f"Expected ERROR log mentioning corrupt/parse, got: {log_ctx.output}",
            )

    def test_missing_file_returns_empty_registry(self) -> None:
        """_load_registry returns {\"crews\": {}} when file is absent (task 3.4)."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            # File does not exist
            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
            ):
                result = registry._load_registry()

        self.assertEqual(result, {"crews": {}})

    def test_permission_error_raises_and_does_not_overwrite(self) -> None:
        """2.4 (D2): an I/O error reading crews.json (e.g. PermissionError)
        propagates out of _load_registry instead of returning {"crews": {}},
        and the existing registry file is left untouched (not clobbered by a
        follow-on save)."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            original = {"crews": {"existing": {"status": "running", "container": "gs-existing"}}}
            reg_path.write_text(json.dumps(original))

            def _raise_permission(*_a, **_k):
                raise PermissionError("read denied")

            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(Path, "read_text", _raise_permission),
                self.assertLogs("transport.registry", level="ERROR"),
            ):
                # Must RAISE, not return {"crews": {}} — the old fallback let a
                # follow-on _save_registry clobber every crew.
                with self.assertRaises(PermissionError):
                    registry._load_registry()

            # The on-disk file must be unchanged (no empty-registry overwrite).
            self.assertEqual(json.loads(reg_path.read_text()), original)

    def test_durability_after_transient_read_error(self) -> None:
        """6.2 (D2 integration): a transient PermissionError on one read does
        not produce an empty registry on the next write. Simulates a transport
        restart sequence: read fails (raises, caller does not save), the error
        clears, a later load+save round-trips the ORIGINAL crews — never an
        empty {"crews": {}} that a stale fallback would have persisted.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"
            original = {"crews": {"c1": {"status": "running", "container": "gs-c1"}}}
            reg_path.write_text(json.dumps(original))

            real_read_text = Path.read_text
            fail = {"on": True}

            def _maybe_fail(self, *a, **k):
                if fail["on"] and self == reg_path:
                    raise PermissionError("transient read error")
                return real_read_text(self, *a, **k)

            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(Path, "read_text", _maybe_fail),
            ):
                # 1) Transient failure: the caller sees it raise. A fail-open
                #    background caller catches and continues WITHOUT saving — so
                #    the file is never overwritten with an empty registry.
                with self.assertRaises(PermissionError):
                    registry._load_registry()
                # Nothing was written during the failure.
                self.assertEqual(json.loads(real_read_text(reg_path)), original)

                # 2) Error clears; a normal load+save round-trips the original.
                fail["on"] = False
                reg = registry._load_registry()
                self.assertEqual(reg, original)
                registry._save_registry(reg)

            # Final on-disk state is the original crews, not an empty registry.
            self.assertEqual(json.loads(reg_path.read_text())["crews"], original["crews"])


class SaveRegistryDirFsyncTests(unittest.TestCase):
    """Regression test: _save_registry() must fsync the parent directory after os.replace.

    ``os.replace`` atomically replaces the destination, but the *directory entry*
    that now points to the new inode may not be durable until the containing
    directory is fsynced.  Without this, a crash immediately after os.replace
    can leave the directory entry lost even though the file data was flushed.
    """

    def test_parent_directory_is_fsynced_after_replace(self) -> None:
        """_save_registry fsyncs DATA_DIR after os.replace so the registry entry survives a crash."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            reg_path = test_dir / "crews.json"

            fsynced_dir_fds: list[int] = []
            real_os_open = os.open
            real_os_fsync = os.fsync
            dir_fds: set[int] = set()

            def tracking_open(path: str, flags: int, mode: int = 0o777) -> int:
                fd = real_os_open(path, flags, mode)
                if os.path.isdir(path):
                    dir_fds.add(fd)
                return fd

            def tracking_fsync(fd: int) -> None:
                if fd in dir_fds:
                    fsynced_dir_fds.append(fd)
                real_os_fsync(fd)

            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch("os.open", side_effect=tracking_open),
                patch("os.fsync", side_effect=tracking_fsync),
            ):
                registry._save_registry({"crews": {}})

            self.assertTrue(
                fsynced_dir_fds,
                "Expected the parent directory to be fsynced after os.replace in _save_registry",
            )
            written = reg_path.read_text()
            self.assertIn("crews", written)


class SaveRegistryFdSentinelTests(unittest.TestCase):
    """Regression test for the fd-sentinel fix in the atomic write path.

    Before the fix, ``fd = -1`` was set inside the ``with os.fdopen()`` block
    body.  The fix moves the sentinel to immediately after the ``os.fdopen()``
    call so the ``finally`` guard cannot double-close an already-owned fd.

    After the TRN-240 refactor the fd operations live in the shared
    ``_write_secret_file`` utility (``_save_registry`` delegates to it), so the
    structural guard is applied there.
    """

    def test_fd_sentinel_placement_in_source(self) -> None:
        """Structural guard: fd = -1 must appear on the line immediately after os.fdopen()."""
        import inspect

        src = inspect.getsource(registry._write_secret_file)
        lines = [l.strip() for l in src.splitlines()]
        fdopen_idx = next(
            (i for i, l in enumerate(lines) if "os.fdopen" in l and not l.startswith("with ")),
            None,
        )
        self.assertIsNotNone(fdopen_idx, "Expected bare os.fdopen() call in _write_secret_file")
        next_nonempty = next(
            (i for i in range(fdopen_idx + 1, len(lines)) if lines[i]),
            None,
        )
        self.assertIsNotNone(next_nonempty, "No line found after os.fdopen()")
        self.assertEqual(
            lines[next_nonempty],
            "fd = -1",
            f"Expected 'fd = -1' immediately after os.fdopen, got: {lines[next_nonempty]!r}",
        )


class WriteCrewSecretDurabilityTests(unittest.TestCase):
    """Tests for _write_crew_secret durability guarantees."""

    def test_parent_directory_is_fsynced(self) -> None:
        """_write_crew_secret fsyncs the parent dir so the entry survives a crash.

        After the secret file is closed, the containing directory is opened
        O_RDONLY and fsynced. Without this the directory entry may be lost on a
        crash immediately after write (trn-139).
        """
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_dir = Path(td)
            secrets_dir = test_dir / registry._SECRETS_DIR_NAME

            fsynced_dir_fds: list[int] = []
            real_os_open = os.open
            real_os_fsync = os.fsync
            dir_fds: set[int] = set()

            def tracking_open(path: str, flags: int, mode: int = 0o777) -> int:
                fd = real_os_open(path, flags, mode)
                if os.path.isdir(path):
                    dir_fds.add(fd)
                return fd

            def tracking_fsync(fd: int) -> None:
                if fd in dir_fds:
                    fsynced_dir_fds.append(fd)
                real_os_fsync(fd)

            with (
                patch.object(registry, "DATA_DIR", test_dir),
                patch("os.open", side_effect=tracking_open),
                patch("os.fsync", side_effect=tracking_fsync),
            ):
                registry._write_crew_secret("gs-demo", "s3cr3t")

            self.assertTrue(
                fsynced_dir_fds,
                "Expected the parent directory to be fsynced after writing the secret",
            )
            written = (secrets_dir / "gs-demo.admiral_secret").read_text()
            self.assertEqual(written, "s3cr3t")


class FindBatchByTaskIdsTests(unittest.TestCase):
    """Tests for _find_batch_by_task_ids (trn-151: subset-match semantics).

    All cases use an in-memory registry patched over REGISTRY_PATH so no
    real disk I/O takes place.
    """

    def _make_registry_with_batch(
        self,
        crew_id: str,
        batch_id: str,
        task_ids: list[str],
    ) -> dict:
        """Return a minimal registry dict containing one crew with one batch."""
        return {
            "crews": {
                crew_id: {
                    "batches": [
                        {
                            "batch_id": batch_id,
                            "task_ids": task_ids,
                            "created_at": "2026-01-01T00:00:00+00:00",
                            "status": "pending",
                        }
                    ]
                }
            }
        }

    def _patch_registry(self, reg: dict, tmp_path: Path):
        """Write *reg* to *tmp_path*/crews.json and return context-manager patches."""
        import tempfile
        reg_path = tmp_path / "crews.json"
        reg_path.write_text(json.dumps(reg))
        return (
            patch.object(registry, "DATA_DIR", tmp_path),
            patch.object(registry, "REGISTRY_PATH", reg_path),
        )

    def test_exact_match_returns_batch(self) -> None:
        """Exact match: provided IDs == batch IDs → batch returned (2.1)."""
        import tempfile
        crew_id = "c-exact"
        batch_id = "b-exact"
        task_ids = ["t1", "t2", "t3"]
        reg = self._make_registry_with_batch(crew_id, batch_id, task_ids)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p1, p2 = self._patch_registry(reg, tmp)
            with p1, p2:
                result = registry._find_batch_by_task_ids(crew_id, task_ids)
        self.assertIsNotNone(result)
        self.assertEqual(result["batch_id"], batch_id)

    def test_subset_match_returns_batch(self) -> None:
        """Subset match: provided IDs ⊂ batch IDs → batch returned (2.2)."""
        import tempfile
        crew_id = "c-sub"
        batch_id = "b-sub"
        batch_task_ids = ["t1", "t2", "t3"]
        provided_task_ids = ["t1", "t2"]  # subset
        reg = self._make_registry_with_batch(crew_id, batch_id, batch_task_ids)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p1, p2 = self._patch_registry(reg, tmp)
            with p1, p2:
                result = registry._find_batch_by_task_ids(crew_id, provided_task_ids)
        self.assertIsNotNone(result)
        self.assertEqual(result["batch_id"], batch_id)

    def test_superset_does_not_match(self) -> None:
        """Superset: provided IDs ⊃ batch IDs → None returned (2.3)."""
        import tempfile
        crew_id = "c-sup"
        batch_id = "b-sup"
        batch_task_ids = ["t1", "t2", "t3"]
        provided_task_ids = ["t1", "t2", "t3", "t4"]  # superset
        reg = self._make_registry_with_batch(crew_id, batch_id, batch_task_ids)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p1, p2 = self._patch_registry(reg, tmp)
            with p1, p2:
                result = registry._find_batch_by_task_ids(crew_id, provided_task_ids)
        self.assertIsNone(result)

    def test_disjoint_does_not_match(self) -> None:
        """Disjoint: no overlap between provided and batch IDs → None returned (2.4)."""
        import tempfile
        crew_id = "c-dis"
        batch_id = "b-dis"
        batch_task_ids = ["t1", "t2", "t3"]
        provided_task_ids = ["tx", "ty"]  # completely disjoint
        reg = self._make_registry_with_batch(crew_id, batch_id, batch_task_ids)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            p1, p2 = self._patch_registry(reg, tmp)
            with p1, p2:
                result = registry._find_batch_by_task_ids(crew_id, provided_task_ids)
        self.assertIsNone(result)


class WriteSecretFileTests(unittest.TestCase):
    """Tests for the shared _write_secret_file atomic 0600 write utility."""

    def test_write_secret_file_creates_with_mode_0600(self) -> None:
        """_write_secret_file creates a new file with mode 0600 and the data."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "nested" / "secret.bin"
            registry._write_secret_file(path, b"super-secret-bytes")
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), b"super-secret-bytes")
            mode = os.stat(path).st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_write_secret_file_accepts_str(self) -> None:
        """A str payload is encoded as UTF-8."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "secret.txt"
            registry._write_secret_file(path, "héllo")
            self.assertEqual(path.read_text(encoding="utf-8"), "héllo")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_write_secret_file_overwrites_and_forces_mode(self) -> None:
        """An existing file is truncated and re-chmodded to 0600."""
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "secret.bin"
            path.write_bytes(b"old-and-longer-content")
            os.chmod(path, 0o644)
            registry._write_secret_file(path, b"new")
            self.assertEqual(path.read_bytes(), b"new")
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class CrewRegistryTests(unittest.TestCase):
    """Tests for CrewRegistry (TRN-240 task 3.1).

    All tests use a temporary directory for the registry path to avoid touching
    real disk state.  The module-level singleton is NOT used here to keep tests
    isolated — each test constructs its own CrewRegistry instance pointing at
    a temp file, with REGISTRY_PATH and DATA_DIR patched.

    The context manager uses the module-level _load_registry()/_save_registry()
    functions so that server.py tests can continue mocking those functions after
    task 3.3 migrates the lock blocks.
    """

    def _make_crew(self, crew_id: str = "demo", **kwargs):
        from transport.crew import Crew
        return Crew(
            crew_id=crew_id,
            container=f"gs-{crew_id}",
            volume=f"gs-vol-{crew_id}",
            home_volume=f"gs-home-{crew_id}",
            cookie="abc",
            status="running",
            **kwargs,
        )

    # ── missing crew returns None ─────────────────────────────────────────────

    def test_get_missing_crew_returns_none(self) -> None:
        """get() returns None for an unknown crew_id."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    result = cr.get("nonexistent")
        self.assertIsNone(result)

    # ── round-trip save/load ──────────────────────────────────────────────────

    def test_put_and_get_roundtrip(self) -> None:
        """put() persists a Crew; get() reads it back correctly."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            crew = self._make_crew("alpha")
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    cr.put(crew)
                # After the context exits (clean), the registry is saved.
                # Re-open to read back from disk.
                with cr:
                    retrieved = cr.get("alpha")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.container, "gs-alpha")
        self.assertEqual(retrieved.cookie, "abc")
        self.assertEqual(retrieved.status, "running")

    # ── context manager auto-save ─────────────────────────────────────────────

    def test_context_manager_saves_on_clean_exit(self) -> None:
        """Changes inside 'with registry:' are persisted on clean exit."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            crew = self._make_crew("beta")
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    cr.put(crew)
            # Read the raw file to confirm it was saved
            saved = json.loads(reg_path.read_text())
        self.assertIn("beta", saved["crews"])
        self.assertEqual(saved["crews"]["beta"]["container"], "gs-beta")

    def test_context_manager_does_not_save_on_exception(self) -> None:
        """Changes inside 'with registry:' are NOT persisted when an exception occurs."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            crew = self._make_crew("gamma")
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                try:
                    with cr:
                        cr.put(crew)
                        raise ValueError("intentional error")
                except ValueError:
                    pass
                # File should not exist or gamma shouldn't be in it
                if reg_path.exists():
                    saved = json.loads(reg_path.read_text())
                    self.assertNotIn("gamma", saved.get("crews", {}))

    # ── remove ────────────────────────────────────────────────────────────────

    def test_remove_deletes_crew(self) -> None:
        """remove() deletes the crew entry; subsequent get() returns None."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            crew = self._make_crew("delta")
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    cr.put(crew)
                with cr:
                    cr.remove("delta")
                with cr:
                    result = cr.get("delta")
        self.assertIsNone(result)

    # ── list ──────────────────────────────────────────────────────────────────

    def test_list_returns_all_crews(self) -> None:
        """list() returns all stored Crew objects."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            cr = registry.CrewRegistry(reg_path)
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    cr.put(self._make_crew("e1"))
                    cr.put(self._make_crew("e2"))
                with cr:
                    crews = cr.list()
        self.assertEqual({c.crew_id for c in crews}, {"e1", "e2"})

    # ── touch ─────────────────────────────────────────────────────────────────

    def test_touch_updates_last_used(self) -> None:
        """touch() updates last_used to approximately now."""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            crew = self._make_crew("zeta")
            cr = registry.CrewRegistry(reg_path)
            before = time.time()
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                with cr:
                    cr.put(crew)
                with cr:
                    cr.touch("zeta")
                with cr:
                    updated = cr.get("zeta")
        self.assertIsNotNone(updated)
        self.assertGreaterEqual(updated.last_used, before)

    # ── concurrent put/get ────────────────────────────────────────────────────

    def test_concurrent_put_get(self) -> None:
        """Concurrent put and get operations serialize correctly via lock.

        Uses a real temp-file registry (no mocking) to verify locking.
        Patches are applied to the global REGISTRY_PATH/DATA_DIR for the
        duration of the test, then threads operate under that single patch.
        """
        import tempfile
        import threading
        with tempfile.TemporaryDirectory() as td:
            reg_path = Path(td) / "crews.json"
            cr = registry.CrewRegistry(reg_path)
            errors: list[str] = []

            def writer() -> None:
                for i in range(5):
                    try:
                        with cr:
                            cr.put(self._make_crew(f"w{i}"))
                    except Exception as e:
                        errors.append(str(e))

            def reader() -> None:
                for i in range(5):
                    try:
                        with cr:
                            cr.list()  # just needs to not raise
                    except Exception as e:
                        errors.append(str(e))

            # Apply the patch in the main thread so all threads see the same state.
            with (
                patch.object(registry, "REGISTRY_PATH", reg_path),
                patch.object(registry, "DATA_DIR", Path(td)),
            ):
                t1 = threading.Thread(target=writer)
                t2 = threading.Thread(target=reader)
                t1.start()
                t2.start()
                t1.join(timeout=10)
                t2.join(timeout=10)

        self.assertEqual(errors, [], f"Concurrent errors: {errors}")


if __name__ == "__main__":
    unittest.main()
