"""Unit tests for transport/registry.py — registry lock protocol.

Covers:
- CrewRegistry context manager: __enter__ acquires lock, __exit__ saves and releases
- CrewRegistry._require_reg: raises outside context block
- CrewRegistry.get / put / remove / list CRUD operations
- CrewRegistry.touch: updates last_used
- CrewRegistry.get_schedules / upsert_schedule / remove_schedule
- _get_crew_schedules / _upsert_crew_schedule / _remove_crew_schedule helpers
- _advance_next_fire_at: interval vs cron vs one_shot vs unknown
- _write_crew_secret / _read_crew_secret: per-crew secret file round-trip
- RegistryCorruptError: raised on bad JSON
- Thread safety: concurrent writers under registry lock

These tests use real file I/O under a tmpdir — the _block_registry_io autouse
fixture in conftest.py is excluded for this file.
"""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from pathlib import Path

from transport.crew import Crew


def _make_registry(tmp_path: Path):
    """Return a CrewRegistry backed by a file in tmp_path.

    Returns (registry, reg_mod, cleanup_fn). Call cleanup_fn() in tearDown
    to restore the module-level globals.
    """
    from transport import registry as reg_mod
    from transport.registry import CrewRegistry

    registry_path = tmp_path / "crews.json"

    # Patch both REGISTRY_PATH and DATA_DIR to point at our tmpdir
    original_data_dir = reg_mod.DATA_DIR
    original_registry_path = reg_mod.REGISTRY_PATH

    reg_mod.DATA_DIR = tmp_path
    reg_mod.REGISTRY_PATH = registry_path

    reg = CrewRegistry(path=registry_path)
    reg._path = registry_path

    return reg, reg_mod, (original_data_dir, original_registry_path)


class TestCrewRegistryCRUD(unittest.TestCase):
    """CrewRegistry.get / put / remove / list CRUD operations."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        self._reg, self._reg_mod, self._orig_data_dir = _make_registry(self._tmp_path)

    def tearDown(self):
        orig_data_dir, orig_reg_path = self._orig_data_dir
        self._reg_mod.DATA_DIR = orig_data_dir
        self._reg_mod.REGISTRY_PATH = orig_reg_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_crew(self, crew_id: str = "abc123") -> Crew:
        return Crew.from_dict(crew_id, {
            "container": f"gs-{crew_id}",
            "image": "localhost/spec-ops:latest",
            "status": "running",
            "launched_at": time.time(),
            "last_used": time.time(),
        })

    def test_get_returns_none_when_empty(self):
        reg = self._reg
        with reg:
            result = reg.get("nonexistent")
        self.assertIsNone(result)

    def test_put_and_get_roundtrip(self):
        reg = self._reg
        crew = self._make_crew("test-crew")
        with reg:
            reg.put(crew)
            result = reg.get("test-crew")
        self.assertIsNotNone(result)
        self.assertEqual(result.crew_id, "test-crew")

    def test_remove_existing_crew(self):
        reg = self._reg
        crew = self._make_crew("to-remove")
        with reg:
            reg.put(crew)
        with reg:
            reg.remove("to-remove")
        with reg:
            result = reg.get("to-remove")
        self.assertIsNone(result)

    def test_remove_nonexistent_is_noop(self):
        reg = self._reg
        with reg:
            reg.remove("no-such-crew")  # should not raise

    def test_list_empty_registry(self):
        reg = self._reg
        with reg:
            crews = reg.list()
        self.assertEqual(crews, [])

    def test_list_multiple_crews(self):
        reg = self._reg
        with reg:
            reg.put(self._make_crew("crew-1"))
            reg.put(self._make_crew("crew-2"))
        with reg:
            crews = reg.list()
        ids = {c.crew_id for c in crews}
        self.assertEqual(ids, {"crew-1", "crew-2"})

    def test_touch_updates_last_used(self):
        reg = self._reg
        crew = self._make_crew("touch-me")
        with reg:
            reg.put(crew)

        old_ts = time.time() - 100
        # Manually backdate last_used
        with reg:
            c = reg.get("touch-me")
            c.last_used = old_ts
            reg.put(c)

        with reg:
            reg.touch("touch-me")
        with reg:
            updated = reg.get("touch-me")
        self.assertGreater(updated.last_used, old_ts)

    def test_put_overwrites_existing(self):
        reg = self._reg
        crew = self._make_crew("overwrite-me")
        with reg:
            reg.put(crew)

        updated_crew = self._make_crew("overwrite-me")
        updated_crew.status = "stopped"
        with reg:
            reg.put(updated_crew)
        with reg:
            result = reg.get("overwrite-me")
        self.assertEqual(result.status, "stopped")

    def test_require_reg_raises_outside_context(self):
        from transport.registry import CrewRegistry, RegistryCorruptError
        reg = self._reg
        with self.assertRaises(RuntimeError):
            reg.get("anything")  # _require_reg should raise

    def test_context_manager_persists_to_file(self):
        """Registry is saved to disk on __exit__."""
        reg = self._reg
        crew = self._make_crew("persist-me")
        with reg:
            reg.put(crew)

        # Verify file was written
        self.assertTrue(self._reg._path.exists() or (self._tmp_path / "crews.json").exists())


class TestCrewRegistryCorrupt(unittest.TestCase):
    """RegistryCorruptError is raised when registry JSON is corrupt."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        self._reg, self._reg_mod, self._orig_data_dir = _make_registry(self._tmp_path)

    def tearDown(self):
        orig_data_dir, orig_reg_path = self._orig_data_dir
        self._reg_mod.DATA_DIR = orig_data_dir
        self._reg_mod.REGISTRY_PATH = orig_reg_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_corrupt_file_raises_registry_corrupt_error(self):
        from transport.registry import RegistryCorruptError
        # Write corrupt JSON to the registry file
        reg_path = self._tmp_path / "crews.json"
        reg_path.write_text("{invalid json{{{{")

        with self.assertRaises(RegistryCorruptError):
            with self._reg:
                pass

    def test_corrupt_file_quarantined(self):
        from transport.registry import RegistryCorruptError
        reg_path = self._tmp_path / "crews.json"
        reg_path.write_text("{bad json")
        try:
            with self._reg:
                pass
        except RegistryCorruptError:
            pass
        # Original file should be gone (renamed to .corrupt)
        self.assertFalse(reg_path.exists())
        corrupt = reg_path.with_name(reg_path.name + ".corrupt")
        self.assertTrue(corrupt.exists())


class TestRegistryScheduleHelpers(unittest.TestCase):
    """CrewRegistry schedule upsert/remove/get helpers."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        self._reg, self._reg_mod, self._orig_data_dir = _make_registry(self._tmp_path)
        # Seed a crew
        crew = Crew.from_dict("sched-crew", {
            "container": "gs-sched-crew",
            "image": "localhost/spec-ops:latest",
            "status": "running",
            "launched_at": time.time(),
            "last_used": time.time(),
        })
        with self._reg:
            self._reg.put(crew)

    def tearDown(self):
        orig_data_dir, orig_reg_path = self._orig_data_dir
        self._reg_mod.DATA_DIR = orig_data_dir
        self._reg_mod.REGISTRY_PATH = orig_reg_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_get_schedules_empty_initially(self):
        with self._reg:
            schedules = self._reg.get_schedules("sched-crew")
        self.assertEqual(schedules, [])

    def test_upsert_schedule_adds_entry(self):
        job = {"job_id": "job-1", "interval_secs": 60, "next_fire_at": time.time() + 60}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", job)
        with self._reg:
            schedules = self._reg.get_schedules("sched-crew")
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["job_id"], "job-1")

    def test_upsert_schedule_updates_existing(self):
        job = {"job_id": "job-1", "interval_secs": 60, "next_fire_at": 9000.0}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", job)
        updated = {"job_id": "job-1", "interval_secs": 120, "next_fire_at": 9999.0}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", updated)
        with self._reg:
            schedules = self._reg.get_schedules("sched-crew")
        self.assertEqual(len(schedules), 1)
        self.assertEqual(schedules[0]["interval_secs"], 120)

    def test_remove_schedule_by_job_id(self):
        job = {"job_id": "job-remove", "interval_secs": 60, "next_fire_at": 9000.0}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", job)
        with self._reg:
            self._reg.remove_schedule("sched-crew", "job-remove")
        with self._reg:
            schedules = self._reg.get_schedules("sched-crew")
        self.assertEqual(schedules, [])

    def test_captain_schedule_upsert_by_type(self):
        """Captain schedules match by type, not job_id."""
        job = {"type": "captain", "enabled": True, "next_fire_at": 9000.0}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", job)
        updated = {"type": "captain", "enabled": False, "next_fire_at": 9001.0}
        with self._reg:
            self._reg.upsert_schedule("sched-crew", updated)
        with self._reg:
            schedules = self._reg.get_schedules("sched-crew")
        captain_scheds = [s for s in schedules if s.get("type") == "captain"]
        self.assertEqual(len(captain_scheds), 1)
        self.assertFalse(captain_scheds[0]["enabled"])


class TestAdvanceNextFireAt(unittest.TestCase):
    """_advance_next_fire_at: interval / one_shot / unknown."""

    def setUp(self):
        from transport.registry import _advance_next_fire_at
        self._advance = _advance_next_fire_at

    def test_interval_advances_by_interval(self):
        before = time.time()
        job = {"interval_secs": 60, "next_fire_at": before}
        self._advance(job)
        self.assertGreater(job["next_fire_at"], before)
        self.assertAlmostEqual(job["next_fire_at"], before + 60, delta=2)

    def test_one_shot_sets_far_future(self):
        job = {"one_shot": True, "next_fire_at": time.time()}
        self._advance(job)
        # Far future sentinel
        self.assertGreater(job["next_fire_at"], 9_000_000_000)

    def test_unknown_schedule_sets_far_future(self):
        """A job with neither interval_secs nor cron_expr is marked as fired."""
        job = {"next_fire_at": time.time()}
        self._advance(job)
        self.assertGreater(job["next_fire_at"], 9_000_000_000)

    def test_mutates_in_place(self):
        job = {"interval_secs": 30, "next_fire_at": 0.0}
        original_job = job
        self._advance(job)
        self.assertIs(job, original_job)


class TestCrewSecretRoundTrip(unittest.TestCase):
    """_write_crew_secret / _read_crew_secret: per-crew secret file persistence."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_read_returns_none_when_absent(self):
        import transport.registry as reg_mod
        original = reg_mod.DATA_DIR
        reg_mod.DATA_DIR = self._tmp_path
        try:
            from transport.registry import _read_crew_secret
            result = _read_crew_secret("nonexistent-crew")
        finally:
            reg_mod.DATA_DIR = original
        self.assertIsNone(result)

    def test_write_and_read_roundtrip(self):
        import transport.registry as reg_mod
        original = reg_mod.DATA_DIR
        reg_mod.DATA_DIR = self._tmp_path
        try:
            from transport.registry import _read_crew_secret, _write_crew_secret
            secret = "deadbeef" * 8  # 64-char hex string
            _write_crew_secret("my-crew", secret)
            result = _read_crew_secret("my-crew")
        finally:
            reg_mod.DATA_DIR = original
        self.assertEqual(result, secret)

    def test_secret_file_mode_is_0600(self):
        import stat
        import transport.registry as reg_mod
        original = reg_mod.DATA_DIR
        reg_mod.DATA_DIR = self._tmp_path
        try:
            from transport.registry import _crew_secret_path, _write_crew_secret
            _write_crew_secret("perm-crew", "secret123")
            path = _crew_secret_path("perm-crew")
        finally:
            reg_mod.DATA_DIR = original
        file_mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(file_mode, 0o600)

    def test_write_overwrites_existing(self):
        import transport.registry as reg_mod
        original = reg_mod.DATA_DIR
        reg_mod.DATA_DIR = self._tmp_path
        try:
            from transport.registry import _read_crew_secret, _write_crew_secret
            _write_crew_secret("overwrite-crew", "first-secret")
            _write_crew_secret("overwrite-crew", "second-secret")
            result = _read_crew_secret("overwrite-crew")
        finally:
            reg_mod.DATA_DIR = original
        self.assertEqual(result, "second-secret")


class TestRegistryLockProtocol(unittest.TestCase):
    """The registry lock serialises concurrent writers."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        self._reg, self._reg_mod, self._orig_data_dir = _make_registry(self._tmp_path)

    def tearDown(self):
        orig_data_dir, orig_reg_path = self._orig_data_dir
        self._reg_mod.DATA_DIR = orig_data_dir
        self._reg_mod.REGISTRY_PATH = orig_reg_path
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_lock_held_inside_context(self):
        """Inside 'with registry:', the _registry_lock is held."""
        from transport.registry import _registry_lock
        reg = self._reg

        lock_held_inside = []
        with reg:
            # Try to acquire the lock from another thread — should fail immediately
            acquired = _registry_lock.acquire(blocking=False)
            lock_held_inside.append(acquired)
            if acquired:
                _registry_lock.release()

        self.assertEqual(lock_held_inside, [False],
                         "Lock should be held (not acquirable) inside 'with registry:'")

    def test_lock_released_after_context(self):
        """After 'with registry:', the lock is released."""
        from transport.registry import _registry_lock
        reg = self._reg

        with reg:
            pass  # enter and exit

        # Lock should be released now
        acquired = _registry_lock.acquire(blocking=False)
        if acquired:
            _registry_lock.release()
        self.assertTrue(acquired, "Lock should be released after 'with registry:' exits")

    def test_concurrent_writers_do_not_corrupt(self):
        """Two threads writing different crews concurrently produce consistent state."""
        reg = self._reg
        errors = []

        def write_crew(crew_id):
            crew = Crew.from_dict(crew_id, {
                "container": f"gs-{crew_id}",
                "image": "localhost/spec-ops:latest",
                "status": "running",
                "launched_at": time.time(),
                "last_used": time.time(),
            })
            try:
                with reg:
                    reg.put(crew)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write_crew, args=(f"crew-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Concurrent writes raised: {errors}")

        # All 5 crews should be present
        with reg:
            crews = reg.list()
        ids = {c.crew_id for c in crews}
        for i in range(5):
            self.assertIn(f"crew-{i}", ids)

    def test_lock_released_on_exception_in_context(self):
        """If an exception is raised inside 'with registry:', the lock is still released."""
        from transport.registry import _registry_lock
        reg = self._reg

        try:
            with reg:
                raise ValueError("intentional error")
        except ValueError:
            pass

        # Lock must be released despite the exception
        acquired = _registry_lock.acquire(blocking=False)
        if acquired:
            _registry_lock.release()
        self.assertTrue(acquired, "Lock should be released even after exception in context")


class TestGetCrewSchedules(unittest.TestCase):
    """_get_crew_schedules: returns the schedules list from a raw reg dict."""

    def test_returns_empty_list_for_missing_crew(self):
        from transport.registry import _get_crew_schedules
        reg = {"crews": {}}
        result = _get_crew_schedules(reg, "no-such-crew")
        self.assertEqual(result, [])

    def test_returns_empty_list_when_no_schedules(self):
        from transport.registry import _get_crew_schedules
        reg = {"crews": {"my-crew": {"container": "gs-my"}}}
        result = _get_crew_schedules(reg, "my-crew")
        self.assertEqual(result, [])

    def test_returns_schedules(self):
        from transport.registry import _get_crew_schedules
        sched = [{"job_id": "j1"}]
        reg = {"crews": {"my-crew": {"schedules": sched}}}
        result = _get_crew_schedules(reg, "my-crew")
        self.assertEqual(result, sched)


class TestUpsertCrewSchedule(unittest.TestCase):
    """_upsert_crew_schedule: inserts or updates by job_id."""

    def test_insert_new_schedule(self):
        from transport.registry import _upsert_crew_schedule
        reg = {"crews": {"c": {}}}
        job = {"job_id": "j1", "interval_secs": 60}
        _upsert_crew_schedule(reg, "c", job)
        self.assertEqual(reg["crews"]["c"]["schedules"], [job])

    def test_update_existing_by_job_id(self):
        from transport.registry import _upsert_crew_schedule
        reg = {"crews": {"c": {"schedules": [{"job_id": "j1", "interval_secs": 60}]}}}
        _upsert_crew_schedule(reg, "c", {"job_id": "j1", "interval_secs": 120})
        self.assertEqual(reg["crews"]["c"]["schedules"][0]["interval_secs"], 120)

    def test_noop_for_missing_crew(self):
        from transport.registry import _upsert_crew_schedule
        reg = {"crews": {}}
        _upsert_crew_schedule(reg, "no-crew", {"job_id": "j1"})
        # No KeyError — just a no-op


class TestRemoveCrewSchedule(unittest.TestCase):
    """_remove_crew_schedule: removes by job_id."""

    def test_remove_existing(self):
        from transport.registry import _remove_crew_schedule
        reg = {"crews": {"c": {"schedules": [{"job_id": "j1"}, {"job_id": "j2"}]}}}
        _remove_crew_schedule(reg, "c", "j1")
        job_ids = [s["job_id"] for s in reg["crews"]["c"]["schedules"]]
        self.assertNotIn("j1", job_ids)
        self.assertIn("j2", job_ids)

    def test_remove_nonexistent_is_noop(self):
        from transport.registry import _remove_crew_schedule
        reg = {"crews": {"c": {"schedules": [{"job_id": "j1"}]}}}
        _remove_crew_schedule(reg, "c", "no-such-job")
        self.assertEqual(len(reg["crews"]["c"]["schedules"]), 1)


if __name__ == "__main__":
    unittest.main()
