"""Unit tests for batch dispatch and registry batch CRUD."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tests.unit.helpers import lifecycle, registry, server  # noqa: F401


class BatchRegistryCRUDTests(unittest.TestCase):
    """Round-trip _write_batch/_get_batch/_update_batch_status/_delete_batch."""

    def _isolated(self) -> ExitStack:
        """Context manager stack: point registry persistence at a temp dir."""
        stack = ExitStack()
        tmp = stack.enter_context(tempfile.TemporaryDirectory())
        stack.enter_context(patch.object(registry, "DATA_DIR", Path(tmp)))
        stack.enter_context(
            patch.object(registry, "REGISTRY_PATH", Path(tmp) / "crews.json")
        )
        return stack

    def _seed_crew(self, crew_id: str = "demo") -> None:
        reg = {"crews": {crew_id: {"container": f"gs-{crew_id}"}}}
        registry._save_registry(reg)

    def test_write_get_roundtrip(self) -> None:
        with self._isolated():
            self._seed_crew()
            entry = registry._write_batch(
                "demo", "b1", ["t1", "t2"], status="pending",
                created_at="2026-01-01T00:00:00+00:00",
            )
            self.assertEqual(entry["batch_id"], "b1")
            self.assertEqual(entry["task_ids"], ["t1", "t2"])
            self.assertEqual(entry["status"], "pending")

            got = registry._get_batch("demo", "b1")
            self.assertEqual(got, entry)
            # A fresh load from disk sees the same record.
            reg = registry._load_registry()
            self.assertEqual(reg["crews"]["demo"]["batches"][0]["batch_id"], "b1")

    def test_write_batch_unknown_crew_returns_none(self) -> None:
        with self._isolated():
            self._seed_crew()
            self.assertIsNone(registry._write_batch("nope", "b1", ["t1"], status="pending"))

    def test_write_batch_upserts_in_place(self) -> None:
        with self._isolated():
            self._seed_crew()
            registry._write_batch("demo", "b1", ["t1"], status="pending")
            registry._write_batch("demo", "b1", ["t1", "t2"], status="partial")
            reg = registry._load_registry()
            batches = reg["crews"]["demo"]["batches"]
            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0]["status"], "partial")
            self.assertEqual(batches[0]["task_ids"], ["t1", "t2"])

    def test_update_batch_status(self) -> None:
        with self._isolated():
            self._seed_crew()
            registry._write_batch("demo", "b1", ["t1"], status="pending")
            updated = registry._update_batch_status("demo", "b1", "complete")
            self.assertEqual(updated["status"], "complete")
            self.assertEqual(registry._get_batch("demo", "b1")["status"], "complete")
            # Unknown batch returns None.
            self.assertIsNone(registry._update_batch_status("demo", "missing", "complete"))

    def test_delete_batch(self) -> None:
        with self._isolated():
            self._seed_crew()
            registry._write_batch("demo", "b1", ["t1"], status="pending")
            self.assertTrue(registry._delete_batch("demo", "b1"))
            self.assertIsNone(registry._get_batch("demo", "b1"))
            # Second delete is a no-op.
            self.assertFalse(registry._delete_batch("demo", "b1"))

    def test_get_batch_missing(self) -> None:
        with self._isolated():
            self._seed_crew()
            self.assertIsNone(registry._get_batch("demo", "nope"))

    def test_find_batch_by_task_ids_match(self) -> None:
        """_find_batch_by_task_ids returns the entry matching the task_ids set."""
        with self._isolated():
            self._seed_crew()
            registry._write_batch(
                "demo", "b-match", ["t1", "t2", "t3"], status="pending",
                created_at="2026-01-01T00:00:00+00:00",
            )
            # Order-independent match.
            found = registry._find_batch_by_task_ids("demo", ["t3", "t1", "t2"])
            self.assertIsNotNone(found)
            self.assertEqual(found["batch_id"], "b-match")

    def test_find_batch_by_task_ids_no_match(self) -> None:
        """Returns None when no batch has exactly these task_ids."""
        with self._isolated():
            self._seed_crew()
            registry._write_batch("demo", "b1", ["t1", "t2"], status="pending")
            self.assertIsNone(registry._find_batch_by_task_ids("demo", ["t1", "t3"]))
            self.assertIsNone(registry._find_batch_by_task_ids("demo", ["t1"]))

    def test_find_batch_by_task_ids_unknown_crew(self) -> None:
        """Returns None for an unknown crew."""
        with self._isolated():
            self._seed_crew()
            self.assertIsNone(registry._find_batch_by_task_ids("nope", ["t1"]))


class NukeRemovesBatchesTests(unittest.TestCase):
    """Nuke drops the crew entry including its batches key."""

    def test_nuke_atomic_write_removes_batches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(registry, "DATA_DIR", Path(tmp)),
                patch.object(registry, "REGISTRY_PATH", Path(tmp) / "crews.json"),
            ):
                reg = {
                    "crews": {
                        "demo": {
                            "container": "gs-demo",
                            "batches": [
                                {"batch_id": "b1", "task_ids": ["t1"], "status": "pending"}
                            ],
                        }
                    }
                }
                registry._save_registry(reg)

                # Simulate the nuke atomic-write body from server.py.
                reg2 = registry._load_registry()
                crew_entry = reg2["crews"].get("demo")
                crew_entry.pop("batches", None)
                reg2["crews"].pop("demo", None)
                registry._save_registry(reg2)

                final = registry._load_registry()
                self.assertNotIn("demo", final["crews"])


class DispatchBatchGuardTests(unittest.TestCase):
    """Mutual exclusion, size validation, and partial-failure path."""

    CREW = {"container": "gs-demo"}

    def test_task_and_tasks_both_supplied(self) -> None:
        result = server.dispatch(task="a", tasks=["a", "b"], crew_id="demo")
        self.assertEqual(result, {"error": "Provide either task or tasks, not both"})

    def test_neither_task_nor_tasks(self) -> None:
        result = server.dispatch(crew_id="demo")
        self.assertEqual(result, {"error": "Provide task or tasks"})

    def test_tasks_too_small(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery") as api,
        ):
            result = server.dispatch(tasks=["only one"], crew_id="demo")
        self.assertIn("at least 2 items", result["error"])
        api.assert_not_called()

    def test_tasks_too_large(self) -> None:
        with (
            patch.dict("os.environ", {"GA_BATCH_MAX_TASKS": "3"}),
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_crew_api_with_recovery") as api,
        ):
            result = server.dispatch(tasks=["a", "b", "c", "d"], crew_id="demo")
        self.assertEqual(result["error"], "tasks exceeds maximum batch size of 3")
        api.assert_not_called()

    def test_batch_invalid_agent_dispatches_nothing(self) -> None:
        with (
            patch.object(server, "_require_crew") as require,
            patch.object(server, "_crew_api_with_recovery") as api,
        ):
            result = server.dispatch(tasks=["a", "b"], agent="not-a-persona", crew_id="demo")
        self.assertIn("Invalid agent", result["error"])
        require.assert_not_called()
        api.assert_not_called()

    def test_batch_full_success(self) -> None:
        calls: list[str] = []

        def _api(crew, crew_id, method, path, **kw):
            calls.append(kw["json"]["task"])
            return {"id": f"task-{len(calls)}"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=_api),
            patch.object(lifecycle, "_write_batch") as write_batch,
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(tasks=["a", "b", "c"], crew_id="demo")

        self.assertEqual(result["status"], "dispatched")
        self.assertEqual(result["task_ids"], ["task-1", "task-2", "task-3"])
        self.assertIn("batch_id", result)
        self.assertEqual(result["agent"], "ghost")
        # Batch recorded with status pending on full success.
        self.assertEqual(write_batch.call_args.kwargs["status"], "pending")

    def test_batch_partial_failure_on_second_call(self) -> None:
        state = {"n": 0}

        def _api(crew, crew_id, method, path, **kw):
            state["n"] += 1
            if state["n"] == 2:
                raise server.CrewUnresponsiveError("crew died")
            return {"id": f"task-{state['n']}"}

        with (
            patch.object(lifecycle, "_require_crew", return_value=self.CREW),
            patch.object(lifecycle, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api_with_recovery", side_effect=_api),
            patch.object(lifecycle, "_write_batch") as write_batch,
            patch.object(lifecycle, "_record_last_task_at"),
        ):
            result = server.dispatch(tasks=["a", "b", "c"], crew_id="demo")

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["task_ids"], ["task-1"])  # only first started
        self.assertIn("crew died", result["error"])
        # Partial batch persisted with status "partial".
        self.assertEqual(write_batch.call_args.kwargs["status"], "partial")


class PickupBatchTests(unittest.TestCase):
    """Lost-member detection and timeout path."""

    CREW = {"container": "gs-demo"}

    def _counts(self, _podman, _container):
        return {"admiral": 0}

    def test_lost_member_detection(self) -> None:
        """One task id returns a 404-style error -> marked lost, batch not done."""

        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            if tid == "id2":
                return {"error": "gateway returned 404 for task", "task_id": tid}
            return {"task_id": tid, "done": True, "result": "ok"}

        out = lifecycle._pickup_batch(
            self.CREW, "demo", ["id1", "id2"], object(), "gs-demo", 0,
            _pickup_single, self._counts,
        )

        self.assertTrue(out["id1"]["done"])
        self.assertEqual(
            out["id2"],
            {"task_id": "id2", "done": False, "lost": True,
             "error": "task not found in gateway"},
        )
        self.assertFalse(out["done"])
        self.assertEqual(out["total_tasks"], 2)
        self.assertEqual(out["completed_tasks"], 1)

    def test_timeout_path(self) -> None:
        """All tasks not-done within the poll window -> reason=timeout, done=False."""

        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            return {"task_id": tid, "done": False}

        with patch.object(lifecycle.time, "sleep") as sleep:
            out = lifecycle._pickup_batch(
                self.CREW, "demo", ["id1", "id2"], object(), "gs-demo", 5,
                _pickup_single, self._counts,
            )

        self.assertFalse(out["done"])
        self.assertEqual(out["reason"], "timeout")
        self.assertEqual(out["completed_tasks"], 0)
        self.assertEqual(out["total_tasks"], 2)
        sleep.assert_called()  # at least one polling round slept

    def test_all_done_marks_batch_complete(self) -> None:
        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            return {"task_id": tid, "done": True, "result": "ok"}

        marked: dict = {}

        def _update(crew_id, batch_id, status):
            marked["args"] = (crew_id, batch_id, status)

        out = lifecycle._pickup_batch(
            self.CREW, "demo", ["id1", "id2"], object(), "gs-demo", 30,
            _pickup_single, self._counts,
            batch_id="b1", update_batch_status=_update,
        )

        self.assertTrue(out["done"])
        self.assertEqual(out["completed_tasks"], 2)
        self.assertEqual(marked["args"], ("demo", "b1", "complete"))

    def test_admiral_mail_early_return(self) -> None:
        """Admiral mail count grows mid-poll -> reason=admiral_mail."""
        seq = iter([{"admiral": 0}, {"admiral": 1}])

        def _counts(_podman, _container):
            return next(seq)

        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            return {"task_id": tid, "done": False}

        with patch.object(lifecycle.time, "sleep"):
            out = lifecycle._pickup_batch(
                self.CREW, "demo", ["id1"], object(), "gs-demo", 30,
                _pickup_single, _counts,
            )

        self.assertEqual(out["reason"], "admiral_mail")
        self.assertFalse(out["done"])


class PickupBatchStatusUpdateTests(unittest.TestCase):
    """Banshee finding fix: verify pickup(task_ids) marks batch complete via _find_batch_by_task_ids."""

    CREW = {"container": "gs-demo"}

    def test_pickup_marks_batch_complete_when_all_done(self) -> None:
        """pickup(task_ids=[...]) looks up the batch_id and calls _update_batch_status(complete)."""
        marked: dict = {}

        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            return {"task_id": tid, "done": True, "result": "ok"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=object()),
            patch.object(server, "_pickup_single", side_effect=_pickup_single),
            patch.object(server, "_read_all_mail_counts", return_value={"admiral": 0}),
            # Simulate registry having a batch record for this task_ids set.
            patch.object(
                server, "_find_batch_by_task_ids",
                return_value={"batch_id": "batch-abc", "task_ids": ["id1", "id2"]},
            ),
            patch.object(server, "_update_batch_status", side_effect=lambda c, b, s: marked.update({"args": (c, b, s)})),
        ):
            out = server.pickup(task_ids=["id1", "id2"], crew_id="demo", timeout_secs=30)

        self.assertTrue(out["done"])
        self.assertEqual(marked.get("args"), ("demo", "batch-abc", "complete"))

    def test_pickup_graceful_when_no_batch_record(self) -> None:
        """pickup(task_ids) works correctly when no matching batch record exists."""

        def _pickup_single(crew, crew_id, tid, podman, container, timeout):
            return {"task_id": tid, "done": True, "result": "ok"}

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=object()),
            patch.object(server, "_pickup_single", side_effect=_pickup_single),
            patch.object(server, "_read_all_mail_counts", return_value={"admiral": 0}),
            patch.object(server, "_find_batch_by_task_ids", return_value=None),
            patch.object(server, "_update_batch_status") as update_mock,
        ):
            out = server.pickup(task_ids=["id1", "id2"], crew_id="demo", timeout_secs=30)

        self.assertTrue(out["done"])
        # No batch_id -> _update_batch_status should NOT be called.
        update_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
