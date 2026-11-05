"""Unit tests for batch dispatch and batch pickup (TRN-292).

- ``TestBatchDispatch`` — _dispatch_batch: successful full batch, partial,
  missing task id, size validation, crew-not-found.
- ``TestBatchPickup``   — _pickup_batch: all-done, snapshot mode, timeout,
  admiral-mail early-return, lost task normalisation, empty task list.

All transport stubs are installed by conftest.py at session scope.
"""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import MagicMock, patch

# ── ensure stubs installed ────────────────────────────────────────────────────
try:
    from tests.unit.conftest import _install_transport_stubs
    _install_transport_stubs()
except Exception:
    pass

try:
    import lifecycle as _lifecycle
except ModuleNotFoundError:
    from transport import lifecycle as _lifecycle


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_crew(crew_id: str = "test-crew") -> dict:
    """Minimal crew dict that _dispatch_batch accepts."""
    return {
        "crew_id": crew_id,
        "container": f"gs-{crew_id}",
        "volume": f"gs-{crew_id}-vol",
        "home_volume": f"gs-{crew_id}-home",
        "status": "running",
        "enrolled_agents": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# T1 — TestBatchDispatch
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchDispatch(unittest.TestCase):
    """_dispatch_batch: batch dispatch scenarios (D1–D6)."""

    def _dispatch(
        self,
        tasks,
        crew_id="test-crew",
        agent="ghost",
        model=None,
        *,
        require_crew_return=None,
        ensure_crew_return=None,
        crew_api_side_effect=None,
        crew_api_return_values=None,
        write_batch_mock=None,
    ):
        """
        Drive _dispatch_batch with patched collaborators.

        ``require_crew_return`` — dict returned by _require_crew (default: fake crew).
        ``ensure_crew_return`` — dict returned by _ensure_crew_running (default: same).
        ``crew_api_side_effect`` — side_effect list for _crew_api_with_recovery.
        ``crew_api_return_values`` — return_value list (used when side_effect is None).
        ``write_batch_mock`` — if provided, used as the _write_batch mock.
        """
        fake_crew = _fake_crew(crew_id)
        rq_return = require_crew_return if require_crew_return is not None else fake_crew
        en_return = ensure_crew_return if ensure_crew_return is not None else fake_crew

        wb_mock = write_batch_mock if write_batch_mock is not None else MagicMock()

        if crew_api_side_effect is not None:
            api_mock = MagicMock(side_effect=crew_api_side_effect)
        elif crew_api_return_values is not None:
            api_mock = MagicMock(side_effect=crew_api_return_values)
        else:
            # Default: each call returns a unique task id
            call_count = [0]
            def _default_return(*args, **kwargs):
                call_count[0] += 1
                return {"id": f"task-{call_count[0]}"}
            api_mock = MagicMock(side_effect=_default_return)

        with patch.object(_lifecycle, "_require_crew", return_value=rq_return), \
             patch.object(_lifecycle, "_ensure_crew_running", return_value=en_return), \
             patch.object(_lifecycle, "_crew_api_with_recovery", api_mock), \
             patch.object(_lifecycle, "_write_batch", wb_mock), \
             patch.object(_lifecycle, "_record_last_task_at"):
            result = _lifecycle._dispatch_batch(
                tasks=tasks,
                agent=agent,
                crew_id=crew_id,
                model=model,
            )
        return result, wb_mock, api_mock

    # ── D1 — successful full batch ─────────────────────────────────────────

    def test_d1_successful_full_batch_status(self):
        """D1: 2 tasks dispatched → status == 'dispatched'."""
        result, _, _ = self._dispatch(["task A", "task B"])
        self.assertEqual(result.get("status"), "dispatched")

    def test_d1_successful_full_batch_task_ids(self):
        """D1: task_ids list has exactly 2 entries."""
        result, _, _ = self._dispatch(["task A", "task B"])
        self.assertEqual(len(result.get("task_ids", [])), 2)

    def test_d1_successful_full_batch_task_id_values(self):
        """D1: task_ids match the values returned by _crew_api_with_recovery."""
        api_returns = [{"id": "tid-alpha"}, {"id": "tid-beta"}]
        result, _, _ = self._dispatch(
            ["task A", "task B"],
            crew_api_return_values=api_returns,
        )
        self.assertIn("tid-alpha", result["task_ids"])
        self.assertIn("tid-beta", result["task_ids"])

    def test_d1_write_batch_called_with_pending(self):
        """D1: _write_batch is called with status='pending' on full success."""
        result, wb, _ = self._dispatch(["task A", "task B"])
        wb.assert_called_once()
        _args, _kwargs = wb.call_args
        # status is the 4th positional arg: _write_batch(crew_id, batch_id, task_ids, status=...)
        # It may be positional or keyword; check both.
        call_kwargs = _kwargs if _kwargs else {}
        # status could be positional (index 3) or keyword
        if "status" in call_kwargs:
            self.assertEqual(call_kwargs["status"], "pending")
        else:
            self.assertEqual(_args[3], "pending")

    def test_d1_batch_id_is_nonempty_string(self):
        """D1: batch_id is a non-empty string in the response."""
        result, _, _ = self._dispatch(["task A", "task B"])
        batch_id = result.get("batch_id", "")
        self.assertIsInstance(batch_id, str)
        self.assertTrue(batch_id, "batch_id should be a non-empty string")

    # ── D2 — partial batch (second spawn raises CrewUnresponsiveError) ─────

    def test_d2_partial_batch_status(self):
        """D2: second spawn raises CrewUnresponsiveError → status == 'partial'."""
        api_effects = [
            {"id": "tid-1"},
            _lifecycle.CrewUnresponsiveError("gateway down"),
        ]
        result, _, _ = self._dispatch(["task A", "task B"], crew_api_side_effect=api_effects)
        self.assertEqual(result.get("status"), "partial")

    def test_d2_partial_batch_only_first_task_id(self):
        """D2: task_ids contains only the one successful id (not the failed one)."""
        api_effects = [
            {"id": "tid-only"},
            _lifecycle.CrewUnresponsiveError("gateway down"),
        ]
        result, _, _ = self._dispatch(["task A", "task B"], crew_api_side_effect=api_effects)
        self.assertEqual(result.get("task_ids"), ["tid-only"])

    def test_d2_partial_batch_error_contains_gateway_down(self):
        """D2: error message contains 'gateway down' (the original exception text)."""
        api_effects = [
            {"id": "tid-1"},
            _lifecycle.CrewUnresponsiveError("gateway down"),
        ]
        result, _, _ = self._dispatch(["task A", "task B"], crew_api_side_effect=api_effects)
        self.assertIn("gateway down", result.get("error", ""))

    def test_d2_partial_batch_error_surfaced(self):
        """D2: partial result carries a non-empty error string."""
        api_effects = [
            {"id": "tid-1"},
            _lifecycle.CrewUnresponsiveError("gateway down"),
        ]
        result, _, _ = self._dispatch(["task A", "task B"], crew_api_side_effect=api_effects)
        self.assertTrue(result.get("error"))

    def test_d2_partial_batch_write_batch_partial(self):
        """D2: _write_batch is called with status='partial' on partial failure."""
        api_effects = [
            {"id": "tid-1"},
            _lifecycle.CrewUnresponsiveError("gateway down"),
        ]
        result, wb, _ = self._dispatch(["task A", "task B"], crew_api_side_effect=api_effects)
        wb.assert_called_once()
        _args, _kwargs = wb.call_args
        call_kwargs = _kwargs if _kwargs else {}
        if "status" in call_kwargs:
            self.assertEqual(call_kwargs["status"], "partial")
        else:
            self.assertEqual(_args[3], "partial")

    # ── D3 — spawn returns no task id ──────────────────────────────────────

    def test_d3_no_task_id_status_partial(self):
        """D3: _crew_api_with_recovery returns {} → status == 'partial'."""
        result, _, _ = self._dispatch(
            ["task A", "task B"],
            crew_api_return_values=[{"id": "tid-1"}, {}],
        )
        self.assertEqual(result.get("status"), "partial")

    def test_d3_no_task_id_error_mentions_no_task_id(self):
        """D3: error message mentions 'no task id'."""
        result, _, _ = self._dispatch(
            ["task A", "task B"],
            crew_api_return_values=[{"id": "tid-1"}, {}],
        )
        self.assertIn("no task id", result.get("error", "").lower())

    # ── D4 — batch too small (1 task) ─────────────────────────────────────

    def test_d4_batch_too_small_returns_error(self):
        """D4: 1-task batch → error mentions 'at least 2'."""
        result, _, _ = self._dispatch(["only one task"])
        self.assertTrue(result.get("error"))
        self.assertIn("at least 2", result.get("error", "").lower())

    # ── D5 — batch too large ───────────────────────────────────────────────

    def test_d5_batch_too_large_returns_error(self):
        """D5: cfg.ga_batch_max_tasks=2, 3 tasks → error mentions 'exceeds maximum'."""
        with patch.object(_lifecycle.cfg, "ga_batch_max_tasks", 2):
            result, _, _ = self._dispatch(["t1", "t2", "t3"])
        self.assertTrue(result.get("error"))
        self.assertIn("exceeds maximum", result.get("error", "").lower())

    def tearDown(self):
        """No env cleanup needed (env mutation no longer controls batch size)."""
        pass

    # ── D6 — crew not found ────────────────────────────────────────────────

    def test_d6_crew_not_found_error_nonempty(self):
        """D6: _require_crew raises ValueError → error is non-empty."""
        with patch.object(_lifecycle, "_require_crew", side_effect=ValueError("crew not found")):
            result = _lifecycle._dispatch_batch(
                tasks=["task A", "task B"],
                agent="ghost",
                crew_id="no-such-crew",
                model=None,
            )
        self.assertTrue(result.get("error"))


# ─────────────────────────────────────────────────────────────────────────────
# T2 — TestBatchPickup
# ─────────────────────────────────────────────────────────────────────────────

class TestBatchPickup(unittest.TestCase):
    """_pickup_batch: pickup state machine and edge cases (P1–P6)."""

    def _pickup(
        self,
        task_ids,
        timeout_secs=0,
        pickup_single_side_effect=None,
        read_all_mail_counts_side_effect=None,
        update_batch_status=None,
        batch_id=None,
    ):
        """
        Drive _pickup_batch with injected callables.

        ``pickup_single_side_effect`` — side_effect list / callable for
            pickup_single mock.
        ``read_all_mail_counts_side_effect`` — side_effect list / callable.
        """
        fake_podman = MagicMock()
        crew = _fake_crew()
        crew_id = "test-crew"
        container = "gs-test-crew"

        ps_mock = MagicMock()
        if pickup_single_side_effect is not None:
            ps_mock.side_effect = pickup_single_side_effect
        else:
            # Default: every task done immediately
            def _default_pickup(c, cid, tid, p, cont, ts):
                return {"task_id": tid, "done": True, "error": ""}
            ps_mock.side_effect = _default_pickup

        ramc_mock = MagicMock()
        if read_all_mail_counts_side_effect is not None:
            ramc_mock.side_effect = read_all_mail_counts_side_effect
        else:
            ramc_mock.return_value = {"admiral": 0}

        ubs_mock = update_batch_status or MagicMock()

        with patch.object(_lifecycle.time, "sleep", MagicMock()):
            result = _lifecycle._pickup_batch(
                crew=crew,
                crew_id=crew_id,
                task_ids=task_ids,
                podman=fake_podman,
                container=container,
                timeout_secs=timeout_secs,
                pickup_single=ps_mock,
                read_all_mail_counts=ramc_mock,
                batch_id=batch_id,
                update_batch_status=ubs_mock,
            )
        return result, ps_mock, ramc_mock, ubs_mock

    # ── P1 — all done on first poll ────────────────────────────────────────

    def test_p1_all_done_first_poll_done_true(self):
        """P1: both tasks done → result['done'] is True."""
        result, _, _, _ = self._pickup(["tid-1", "tid-2"])
        self.assertTrue(result.get("done"))

    def test_p1_update_batch_status_called_complete(self):
        """P1: update_batch_status called with 'complete' on full success."""
        ubs = MagicMock()
        self._pickup(["tid-1", "tid-2"], batch_id="batch-abc", update_batch_status=ubs)
        ubs.assert_called_once()
        args, _ = ubs.call_args
        self.assertEqual(args[2], "complete")

    def test_p1_completed_and_total_tasks_counts(self):
        """P1: completed_tasks == 2 and total_tasks == 2 when both tasks done."""
        result, _, _, _ = self._pickup(["tid-1", "tid-2"])
        self.assertEqual(result.get("completed_tasks"), 2)
        self.assertEqual(result.get("total_tasks"), 2)

    # ── P2 — snapshot mode (timeout=0) ────────────────────────────────────

    def test_p2_snapshot_mode_not_all_done(self):
        """P2: timeout=0, one done one pending → result['done'] False."""
        call_count = [0]
        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            call_count[0] += 1
            # Only first task is done
            return {"task_id": tid, "done": call_count[0] == 1, "error": ""}

        result, _, _, _ = self._pickup(
            ["tid-1", "tid-2"],
            timeout_secs=0,
            pickup_single_side_effect=_pickup_side_effect,
        )
        self.assertFalse(result.get("done"))

    def test_p2_snapshot_mode_returns_immediately(self):
        """P2: timeout=0 returns without sleeping (snapshot mode)."""
        sleep_mock = MagicMock()
        call_count = [0]
        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            call_count[0] += 1
            return {"task_id": tid, "done": False, "error": ""}

        with patch.object(_lifecycle.time, "sleep", sleep_mock):
            _lifecycle._pickup_batch(
                crew=_fake_crew(),
                crew_id="test-crew",
                task_ids=["tid-1", "tid-2"],
                podman=MagicMock(),
                container="gs-test",
                timeout_secs=0,
                pickup_single=MagicMock(side_effect=_pickup_side_effect),
                read_all_mail_counts=MagicMock(return_value={"admiral": 0}),
            )
        sleep_mock.assert_not_called()

    # ── P3 — wall-time timeout ────────────────────────────────────────────

    def test_p3_timeout_reason(self):
        """P3: timeout=3, tasks never done → result['reason'] == 'timeout'."""
        monotonic_values = iter([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.1, 100.0])

        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            return {"task_id": tid, "done": False, "error": ""}

        with patch.object(_lifecycle.time, "monotonic", side_effect=monotonic_values), \
             patch.object(_lifecycle.time, "sleep", MagicMock()):
            result = _lifecycle._pickup_batch(
                crew=_fake_crew(),
                crew_id="test-crew",
                task_ids=["tid-1", "tid-2"],
                podman=MagicMock(),
                container="gs-test",
                timeout_secs=3,
                pickup_single=MagicMock(side_effect=_pickup_side_effect),
                read_all_mail_counts=MagicMock(return_value={"admiral": 0}),
            )
        self.assertEqual(result.get("reason"), "timeout")

    def test_p3_done_false_on_timeout(self):
        """P3: result['done'] is False on timeout."""
        monotonic_values = iter([0.0, 0.5, 3.1, 100.0])

        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            return {"task_id": tid, "done": False, "error": ""}

        with patch.object(_lifecycle.time, "monotonic", side_effect=monotonic_values), \
             patch.object(_lifecycle.time, "sleep", MagicMock()):
            result = _lifecycle._pickup_batch(
                crew=_fake_crew(),
                crew_id="test-crew",
                task_ids=["tid-1", "tid-2"],
                podman=MagicMock(),
                container="gs-test",
                timeout_secs=3,
                pickup_single=MagicMock(side_effect=_pickup_side_effect),
                read_all_mail_counts=MagicMock(return_value={"admiral": 0}),
            )
        self.assertFalse(result.get("done"))

    # ── P4 — admiral-mail early return ────────────────────────────────────

    def test_p4_admiral_mail_early_return_reason(self):
        """P4: admiral mail count rises on second call → reason == 'admiral_mail'."""
        # First call (initial baseline) returns 0; second call returns 1.
        mail_call_count = [0]
        def _read_mail(p, c):
            mail_call_count[0] += 1
            if mail_call_count[0] <= 1:
                return {"admiral": 0}
            return {"admiral": 1}

        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            return {"task_id": tid, "done": False, "error": ""}

        with patch.object(_lifecycle.time, "monotonic", side_effect=[0.0, 0.5, 1.0, 100.0]), \
             patch.object(_lifecycle.time, "sleep", MagicMock()):
            result = _lifecycle._pickup_batch(
                crew=_fake_crew(),
                crew_id="test-crew",
                task_ids=["tid-1", "tid-2"],
                podman=MagicMock(),
                container="gs-test",
                timeout_secs=60,
                pickup_single=MagicMock(side_effect=_pickup_side_effect),
                read_all_mail_counts=MagicMock(side_effect=_read_mail),
            )
        self.assertEqual(result.get("reason"), "admiral_mail")

    def test_p4_admiral_mail_done_false(self):
        """P4: admiral-mail early return → result['done'] is False."""
        mail_call_count = [0]
        def _read_mail(p, c):
            mail_call_count[0] += 1
            if mail_call_count[0] <= 1:
                return {"admiral": 0}
            return {"admiral": 1}

        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            return {"task_id": tid, "done": False, "error": ""}

        with patch.object(_lifecycle.time, "monotonic", side_effect=[0.0, 0.5, 1.0, 100.0]), \
             patch.object(_lifecycle.time, "sleep", MagicMock()):
            result = _lifecycle._pickup_batch(
                crew=_fake_crew(),
                crew_id="test-crew",
                task_ids=["tid-1", "tid-2"],
                podman=MagicMock(),
                container="gs-test",
                timeout_secs=60,
                pickup_single=MagicMock(side_effect=_pickup_side_effect),
                read_all_mail_counts=MagicMock(side_effect=_read_mail),
            )
        self.assertFalse(result.get("done"))

    # ── P5 — lost task_id normalisation ──────────────────────────────────

    def test_p5_lost_task_marked(self):
        """P5: pickup_single returns 404-shaped error → result[tid]['lost'] True."""
        def _pickup_side_effect(c, cid, tid, p, cont, ts):
            return {"task_id": tid, "done": False, "error": "404 not found"}

        result, _, _, _ = self._pickup(
            ["lost-tid"],
            timeout_secs=0,
            pickup_single_side_effect=_pickup_side_effect,
        )
        self.assertTrue(result.get("lost-tid", {}).get("lost"))

    # ── P6 — empty task list ──────────────────────────────────────────────

    def test_p6_empty_task_list_total_tasks_zero(self):
        """P6: task_ids=[] → total_tasks == 0."""
        result, _, _, _ = self._pickup([])
        self.assertEqual(result.get("total_tasks"), 0)

    def test_p6_empty_task_list_done_false(self):
        """P6: task_ids=[] → done is False (no tasks = not all done)."""
        result, _, _, _ = self._pickup([])
        self.assertFalse(result.get("done"))


if __name__ == "__main__":
    unittest.main()
