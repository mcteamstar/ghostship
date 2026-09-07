"""Unit tests for ``transport.registry`` — crew registry + schedule persistence.

TRN-85 migration target for classes whose function-under-test is defined in
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
    """Tests for _advance_next_fire_at (D4 in TRN-39 design.md)."""

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
    """Tests for _save_registry durability guarantees (TRN-124)."""

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

            mock_fsync.assert_called_once()
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
        """Corrupt crews.json raises, creates .corrupt, removes original (task 3.3)."""
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
                with self.assertRaises(json.JSONDecodeError):
                    registry._load_registry()
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


class SaveRegistryFdSentinelTests(unittest.TestCase):
    """Regression test for the fd-sentinel fix in _save_registry() (TRN-139).

    Before TRN-139, ``fd = -1`` was set inside the ``with os.fdopen()`` block
    body.  The fix moves the sentinel to immediately after the ``os.fdopen()``
    call so the ``finally`` guard cannot double-close an already-owned fd.
    """

    def test_fd_sentinel_placement_in_source(self) -> None:
        """Structural guard: fd = -1 must appear on the line immediately after os.fdopen()."""
        import inspect

        src = inspect.getsource(registry._save_registry)
        lines = [l.strip() for l in src.splitlines()]
        fdopen_idx = next(
            (i for i, l in enumerate(lines) if "os.fdopen" in l and not l.startswith("with ")),
            None,
        )
        self.assertIsNotNone(fdopen_idx, "Expected bare os.fdopen() call in _save_registry")
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
    """Tests for _write_crew_secret durability guarantees (TRN-139)."""

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


if __name__ == "__main__":
    unittest.main()
