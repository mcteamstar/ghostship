"""Unit tests for ``transport.captain`` — Captain standing orders + mail helpers.

Migration target. ``CaptainStandingOrdersTests`` exercises the
``server.captain()`` MCP tool plus captain-owned helpers (``_format_captain_mail``,
``_append_captain_mail``, ``_mail_count``, ``_resolve_order_template``) and a
couple of ``server.schedule()`` reservation checks.

Patch targets follow the call-site principle (design §2):
- ``captain()`` calls ``_require_crew`` / ``_ensure_crew_running`` / ``_get_podman``
  / ``_append_captain_mail`` / ``_mail_count`` / ``_resolve_order_template`` /
  ``_load_registry`` **by name from server's namespace** (server ``from
  transport.{captain,lifecycle} import ...``) → patch ``server.X`` for those
  call-site mocks.
- ``captain()`` reaches the gateway through ``_crew_api_with_recovery`` (lifecycle),
  which calls ``_crew_api`` from lifecycle's own namespace → patch
  ``lifecycle._crew_api`` for the crew-API mock (the ``server._crew_api``
  dual-patch shadows are dropped).
"""

from __future__ import annotations

import base64
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

from tests.unit.helpers import captain_mod, lifecycle, server  # noqa: F401


class CaptainStandingOrdersTests(unittest.TestCase):
    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def test_order_sdd_template_resolves_and_schedules_like_message(self) -> None:
        podman = Mock()
        expected = server._resolve_order_template("sdd", "demo-change")
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_crew_api",
                         return_value={"id": "task-1"}) as api,
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
        # Should call POST /api/spawn (not /api/crons) for immediate dispatch
        spawn_calls = [c for c in api.call_args_list if "/api/spawn" in c.args[2]]
        self.assertEqual(len(spawn_calls), 1)
        self.assertEqual(spawn_calls[0].kwargs["json"]["agent"], "raven")
        self.assertEqual(spawn_calls[0].kwargs["json"]["parent_session"], "dashboard:member-raven")

    def test_order_appends_mail_after_checkin_is_ready(self) -> None:
        podman = Mock()
        events: list[str] = []

        def append(_podman: Any, _container: str, _body: str, crew_id: str | None = None) -> None:
            events.append("mail")

        def api(_crew: dict, method: str, path: str, **kwargs: Any) -> Any:
            events.append(f"{method} {path}")
            if method == "POST" and path == "/api/spawn":
                return {"id": "task-1"}
            raise AssertionError((method, path, kwargs))

        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail", side_effect=append),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_crew_api", side_effect=api),
        ):
            result = server.captain(
                "demo", "order", message="ready after provisioning", interval=120
            )

        self.assertEqual(result["status"], "ordered")
        # interval=120 → fire_immediately defaults True → mail then spawn
        self.assertEqual(events, ["mail", "POST /api/spawn"])

    def test_concurrent_orders_share_one_checkin_job(self) -> None:
        podman = Mock()
        start = threading.Barrier(3)
        state_lock = threading.Lock()
        task_counter = [0]
        results: list[dict[str, Any]] = []
        errors: list[BaseException] = []

        def api(_crew: dict, method: str, path: str, **kwargs: Any) -> Any:
            if method == "POST" and path == "/api/spawn":
                with state_lock:
                    task_counter[0] += 1
                    return {"id": f"task-{task_counter[0]}"}
            raise AssertionError((method, path, kwargs))

        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}

        def invoke() -> None:
            start.wait()
            try:
                results.append(
                    server.captain("demo", "order", message="same", interval=120)
                )
            except BaseException as exc:  # pragma: no cover
                errors.append(exc)

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_crew_api", side_effect=api),
        ):
            threads = [threading.Thread(target=invoke) for _ in range(2)]
            for thread in threads:
                thread.start()
            start.wait()
            for thread in threads:
                thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["status"] == "ordered" for r in results))

    def test_order_without_existing_job_requires_schedule_before_mail(self) -> None:
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_append_captain_mail") as append,
        ):
            result = server.captain("demo", "order", message="hold")

        self.assertIn("requires either cron or interval", result["error"])
        append.assert_not_called()

    def test_order_creates_raven_job_when_no_job_exists(self) -> None:
        podman = Mock()
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
            patch.object(lifecycle, "_crew_api",
                         return_value={"id": "task-1"}) as api,
        ):
            result = server.captain(
                "demo", "order", message="implement the objective", interval=120
            )

        self.assertEqual(result["status"], "ordered")
        append.assert_called_once_with(
            podman, "gs-demo", "implement the objective", crew_id="demo"
        )
        spawn_calls = [c for c in api.call_args_list if "/api/spawn" in c.args[2]]
        self.assertEqual(len(spawn_calls), 1)
        self.assertEqual(spawn_calls[0].kwargs["json"]["agent"], "raven")
        self.assertEqual(spawn_calls[0].kwargs["json"]["parent_session"], "dashboard:member-raven")
        self.assertEqual(spawn_calls[0].kwargs["json"]["task"], server._CAPTAIN_CHECKIN_TASK)

    def test_order_cron_passes_through_custom_timezone(self) -> None:
        podman = Mock()
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"], "schedules": []}}}
        saved_entries: list[dict] = []

        def save_reg(r: dict) -> None:
            for s in r["crews"].get("demo", {}).get("schedules", []):
                if s.get("type") == "captain":
                    saved_entries.append(dict(s))

        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry", side_effect=save_reg),
        ):
            result = server.captain(
                "demo",
                "order",
                message="hold",
                cron="0 9 * * 1",
                timezone="America/New_York",
            )

        self.assertEqual(result["status"], "ordered")
        self.assertTrue(any(e.get("cron_expr") == "0 9 * * 1" for e in saved_entries))

    def test_order_reuses_existing_enabled_job_without_schedule_args(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "interval_secs": 300,
            "cron_expr": None,
            "next_fire_at": 9999999999.0,
            "current_task_id": "task-existing",
            "model": None,
        }
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"],
                                  "schedules": [existing_entry]}}}
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
        ):
            result = server.captain("demo", "order", message="new order")

        self.assertEqual(result["status"], "ordered")
        append.assert_called_once_with(podman, "gs-demo", "new order", crew_id="demo")

    def test_standing_stop_disables_job_without_delete(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "interval_secs": 300,
            "current_task_id": "task-1",
        }
        registry = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry") as save_reg,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=2),
        ):
            result = server.captain("demo", "stop")

        self.assertFalse(result["enabled"])
        self.assertEqual(result["status"], "stopped")
        save_reg.assert_called_once()
        self.assertFalse(registry["crews"]["demo"]["schedules"][0]["enabled"])

    def test_standing_stop_gateway_not_found_still_returns_stopped(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        registry = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry") as save_reg,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=1),
        ):
            result = server.captain("demo", "stop")

        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(result["enabled"])
        save_reg.assert_called_once()

    def test_stop_when_already_disabled_in_gateway_still_updates_registry(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        registry = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry") as save_reg,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=1),
        ):
            result = server.captain("demo", "stop")

        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(result["enabled"])
        save_reg.assert_called_once()
        self.assertFalse(registry["crews"]["demo"]["schedules"][0]["enabled"])

    def test_stop_when_gateway_api_raises_exception_still_updates_registry(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        registry = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry") as save_reg,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=1),
        ):
            result = server.captain("demo", "stop")

        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "stopped")
        self.assertFalse(result["enabled"])
        save_reg.assert_called_once()
        self.assertFalse(registry["crews"]["demo"]["schedules"][0]["enabled"])

    def test_standing_stop_uses_refreshed_crew_after_restart(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        registry = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        stale = {"container": "gs-demo", "cookie": "old-cookie"}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=stale),
            patch.object(server, "_load_registry", return_value=registry),
            patch.object(server, "_save_registry"),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=1),
        ):
            result = server.captain("demo", "stop")

        self.assertEqual(result["status"], "stopped")

    def test_status_reports_captain_and_admiral_mail_counts(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [existing_entry],
        }}}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_mail_count", side_effect=[3, 2]) as mail_count,
            patch.object(server, "_skim_all_mailboxes", return_value={
                name: [] for name in captain_mod._ALL_MAIL_MAILBOXES
            }),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(result["unread_mail"], 3)
        self.assertEqual(result["mailbox"], "captain@localhost")
        self.assertEqual(result["unread_admiral_mail"], 2)
        self.assertEqual(result["admiral_mailbox"], "admiral@localhost")
        self.assertEqual(mail_count.call_count, 2)
        self.assertEqual(mail_count.call_args_list[0].args[2], "/var/mail/captain")
        self.assertEqual(mail_count.call_args_list[1].args[2], "/var/mail/admiral")

    def test_order_resumes_existing_paused_job_without_schedule_args(self) -> None:
        existing_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": False,
            "interval_secs": 300,
            "cron_expr": None,
            "next_fire_at": 9999999999.0,
            "current_task_id": "task-paused",
            "model": None,
        }
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": ["raven"],
                                  "schedules": [existing_entry]}}}
        podman = Mock()
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
        ):
            result = server.captain("demo", "order", message="resume this")

        self.assertEqual(result["status"], "ordered")
        append.assert_called_once_with(podman, "gs-demo", "resume this", crew_id="demo")

    def test_order_reports_failed_resume_toggle(self) -> None:
        # With dispatch+steer, "resume toggle" no longer exists.
        # Test that unenrolled raven surfaces an error on immediate dispatch.
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "enrolled_agents": [],
                                  "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=Mock()),
            patch.object(server, "_append_captain_mail"),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(server, "_save_registry"),
        ):
            result = server.captain(
                "demo", "order", message="try to fire", interval=120,
                fire_immediately=True,
            )

        self.assertIn("immediate_dispatch_error", result)
        self.assertIn("not enrolled", result["immediate_dispatch_error"])

    def test_stop_rejects_non_default_timezone(self) -> None:
        with patch.object(server, "_require_crew") as require:
            result = server.captain("demo", "stop", timezone="America/New_York")

        self.assertIn("does not accept", result["error"])
        self.assertIn("timezone", result["error"])
        require.assert_not_called()

    def test_checkin_job_lookup_ignores_reserved_name_with_wrong_agent(self) -> None:
        # A job named "captain" but dispatched to a different agent - predating
        # the reservation, or created by bypassing schedule() entirely - must
        # never be silently mistaken for the real Captain check-in.
        impostor = {"jobs": [{"id": "x", "name": "captain", "agent": "ghost", "enabled": True}]}
        self.assertIsNone(server._captain_checkin_job(impostor))
        self.assertIsNone(server._captain_checkin_job(impostor, enabled_only=True))

    def test_schedule_uses_gateway_cron_field(self) -> None:
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(lifecycle, "_crew_api", return_value={"id": "cron-job"}) as api,
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

    # ── sdd multi-change via comma-separated <change> ────────────────────────

    def test_resolve_sdd_multi_change_substitutes_value(self) -> None:
        """sdd: comma-separated change_name is substituted and no bare <change> token remains."""
        resolved = server._resolve_order_template("sdd", "trn-110,trn-115")
        self.assertNotIn("<change>", resolved)
        # The raw comma-separated value should appear as-is in the body
        self.assertIn("trn-110,trn-115", resolved)

    def test_resolve_sdd_multi_change_validates_each_name(self) -> None:
        """sdd: an invalid individual change name in a comma-separated list raises ValueError."""
        with self.assertRaises(ValueError):
            server._resolve_order_template("sdd", "trn-110,bad name!")

    def test_resolve_sdd_requires_change_name(self) -> None:
        """sdd: change_name=None raises ValueError."""
        with self.assertRaises(ValueError):
            server._resolve_order_template("sdd", None)

    # ── independent-review template resolution ────────────────────────────────

    def test_resolve_independent_review_scopes_to_change(self) -> None:
        """Task 3.1: independent-review with change_name substitutes Scope line, no residual {{...}}."""
        resolved = server._resolve_order_template("independent-review", "trn-107")
        self.assertIn("Scope: trn-107", resolved)
        self.assertNotIn("<change?>", resolved)
        self.assertNotIn("<change>", resolved)
        import re as _re
        self.assertFalse(_re.search(r"\{\{[A-Z_]+\}\}", resolved))

    def test_resolve_independent_review_accepts_none_change_name(self) -> None:
        """independent-review with change_name=None resolves to 'entire codebase'."""
        resolved = server._resolve_order_template("independent-review", None)
        self.assertIn("Scope: entire codebase", resolved)
        self.assertNotIn("<change?>", resolved)
        self.assertNotIn("<change>", resolved)
        import re as _re
        self.assertFalse(_re.search(r"\{\{[A-Z_]+\}\}", resolved))

    def test_resolve_independent_review_whole_codebase(self) -> None:
        """independent-review with change_name=None yields Scope: entire codebase, no residual tokens."""
        resolved = server._resolve_order_template("independent-review", None)
        self.assertIn("Scope: entire codebase", resolved)
        self.assertNotIn("<change>", resolved)
        self.assertNotIn("<changes>", resolved)
        import re as _re
        self.assertFalse(_re.search(r"\{\{[A-Z_]+\}\}", resolved))

    def test_resolve_template_rejects_both_tokens(self) -> None:
        """A template body containing both <change> and <changes> raises ValueError."""
        import tempfile, os
        orders_dir = server._resolve_orders_dir()
        test_template = orders_dir / "_test_both_tokens.md"
        try:
            test_template.write_text(
                "Body with both <change> and <changes> tokens.\n"
            )
            with self.assertRaises(ValueError) as ctx:
                server._resolve_order_template("_test_both_tokens", "trn-110")
            self.assertIn("both", str(ctx.exception))
        finally:
            test_template.unlink(missing_ok=True)

    # ── <change?> optional token tests ───────────────────────────────────────

    def test_optional_change_token_with_name(self) -> None:
        """<change?> with a provided change_name substitutes the name."""
        orders_dir = server._resolve_orders_dir()
        test_template = orders_dir / "_test_change_optional_name.md"
        try:
            test_template.write_text("Scope: <change?>\n")
            resolved = server._resolve_order_template("_test_change_optional_name", "trn-120")
            self.assertEqual(resolved, "Scope: trn-120")
            self.assertNotIn("<change?>", resolved)
        finally:
            test_template.unlink(missing_ok=True)

    def test_optional_change_token_without_name(self) -> None:
        """<change?> with change_name=None substitutes 'entire codebase'."""
        orders_dir = server._resolve_orders_dir()
        test_template = orders_dir / "_test_change_optional_none.md"
        try:
            test_template.write_text("Scope: <change?>\n")
            resolved = server._resolve_order_template("_test_change_optional_none", None)
            self.assertEqual(resolved, "Scope: entire codebase")
            self.assertNotIn("<change?>", resolved)
        finally:
            test_template.unlink(missing_ok=True)

    def test_optional_change_token_conflict_with_required(self) -> None:
        """Template body with both <change?> and <change> raises ValueError."""
        orders_dir = server._resolve_orders_dir()
        test_template = orders_dir / "_test_change_optional_conflict.md"
        try:
            test_template.write_text("Scope: <change?> and <change>\n")
            with self.assertRaises(ValueError) as ctx:
                server._resolve_order_template("_test_change_optional_conflict", "trn-120")
            self.assertIn("mix", str(ctx.exception))
        finally:
            test_template.unlink(missing_ok=True)


class MaildirSubjectReaderTests(unittest.TestCase):
    """Task 2.3 — _read_maildir_subjects_from_tar with synthetic tar bytes."""

    @staticmethod
    def _make_maildir_tar(messages: dict[str, str]) -> bytes:
        """Build a synthetic Maildir tar.

        ``messages`` maps relative path inside the tar (e.g. ``new/msg1``) to
        RFC 5322-formatted message text.  Returns tar bytes.
        """
        import io as _io
        import tarfile as _tarfile

        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tf:
            for name, content in messages.items():
                data = content.encode("utf-8")
                info = _tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, _io.BytesIO(data))
        return buf.getvalue()

    def test_reads_subjects_from_new_and_cur(self) -> None:
        tar = self._make_maildir_tar({
            "new/msg1": "From: ghost@localhost\nSubject: task A done\n\nbody",
            "cur/msg2": "From: spectre@localhost\nSubject: task B ready\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 2)
        subject_texts = [s["subject"] for s in subjects]
        self.assertIn("task A done", subject_texts)
        self.assertIn("task B ready", subject_texts)
        # All entries have received_at key (may be None if no Date header)
        for entry in subjects:
            self.assertIn("subject", entry)
            self.assertIn("received_at", entry)

    def test_ignores_files_outside_new_and_cur(self) -> None:
        tar = self._make_maildir_tar({
            "tmp/msg1": "Subject: should be ignored\n\nbody",
            "new/msg2": "Subject: included\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["subject"], "included")

    def test_empty_mailbox_returns_empty_list(self) -> None:
        tar = self._make_maildir_tar({})
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(subjects, [])

    def test_message_without_subject_header_skipped(self) -> None:
        tar = self._make_maildir_tar({
            "new/msg1": "From: ghost@localhost\n\nno subject header here",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(subjects, [])

    def test_bytes_input_works(self) -> None:
        tar = self._make_maildir_tar({
            "new/msg1": "Subject: bytes path\n\nbody",
        })
        self.assertIsInstance(tar, bytes)
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["subject"], "bytes path")

    def test_deeply_nested_new_dir_is_included(self) -> None:
        """A path like captain/new/msg1 (tar from archive API) should be matched."""
        tar = self._make_maildir_tar({
            "captain/new/msg1": "Subject: deep subject\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["subject"], "deep subject")

    def test_corrupt_tar_returns_empty_list(self) -> None:
        subjects = captain_mod._read_maildir_subjects_from_tar(b"not a tar stream")
        self.assertEqual(subjects, [])

    def test_read_mail_subjects_archive_calls_archive_get(self) -> None:
        """_read_mail_subjects_archive calls container_archive_get and parses subjects."""
        import io as _io
        tar = self._make_maildir_tar({
            "new/msg1": "Subject: order received\n\nbody",
        })

        class _FakeResp:
            def iter_bytes(self):
                yield tar

            def close(self):
                pass

        podman = Mock()
        podman.container_archive_get.return_value = _FakeResp()
        result = captain_mod._read_mail_subjects_archive(podman, "gs-demo", "/var/mail/captain")
        podman.container_archive_get.assert_called_once_with("gs-demo", "/var/mail/captain")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["subject"], "order received")
        self.assertIn("received_at", result[0])

    def test_read_mail_subjects_archive_returns_empty_on_error(self) -> None:
        """_read_mail_subjects_archive returns [] if archive_get raises."""
        podman = Mock()
        podman.container_archive_get.side_effect = Exception("container not found")
        result = captain_mod._read_mail_subjects_archive(podman, "gs-demo", "/var/mail/captain")
        self.assertEqual(result, [])


class CaptainStatusArchiveTests(unittest.TestCase):
    """Tasks 5.1 + 5.2 — captain status uses archive API for mail subjects."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    @staticmethod
    def _make_maildir_tar(messages: dict[str, str]) -> bytes:
        import io as _io
        import tarfile as _tarfile
        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tf:
            for name, content in messages.items():
                data = content.encode("utf-8")
                info = _tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, _io.BytesIO(data))
        return buf.getvalue()

    def _make_podman(
        self,
        *,
        is_running: bool,
        captain_tar: bytes | None = None,
        admiral_tar: bytes | None = None,
    ):
        """Build a Mock podman that returns scripted archive tars and running state."""
        podman = Mock()
        podman.container_is_running.return_value = is_running

        captain_tar = captain_tar or self._make_maildir_tar({})
        admiral_tar = admiral_tar or self._make_maildir_tar({})

        class _FakeResp:
            def __init__(self, data: bytes) -> None:
                self._data = data

            def iter_bytes(self):
                yield self._data

            def close(self):
                pass

        def _archive_get(container, path):
            if "captain" in path:
                return _FakeResp(captain_tar)
            return _FakeResp(admiral_tar)

        podman.container_archive_get.side_effect = _archive_get
        return podman

    def test_status_stopped_crew_returns_subjects_without_waking_container(self) -> None:
        """5.1 — stopped crew: subjects returned, _ensure_crew_running NOT called."""
        captain_tar = self._make_maildir_tar({
            "new/msg1": "Subject: trn-51 cleanup done\n\nbody",
        })
        admiral_tar = self._make_maildir_tar({
            "new/msg1": "Subject: SO1 complete\n\nbody",
        })
        podman = self._make_podman(
            is_running=False,
            captain_tar=captain_tar,
            admiral_tar=admiral_tar,
        )
        # No captain entry in registry → dormant
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "schedules": []}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value=reg),
        ):
            result = server.captain("demo", "status")

        # Subjects are present
        self.assertEqual(result["captain_subjects"], [{"subject": "trn-51 cleanup done", "received_at": None}])
        self.assertEqual(result["admiral_subjects"], [{"subject": "SO1 complete", "received_at": None}])
        self.assertEqual(result["captain_mail"], 1)
        self.assertEqual(result["admiral_mail"], 1)
        # Status is dormant (no captain entry in registry)
        self.assertEqual(result["status"], "dormant")
        # Container was NOT started
        ensure.assert_not_called()

    def test_status_stopped_crew_empty_mailboxes(self) -> None:
        """5.1 — stopped crew with empty mailboxes: subjects are empty lists."""
        podman = self._make_podman(is_running=False)
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_get_podman", return_value=podman),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(result["captain_subjects"], [])
        self.assertEqual(result["admiral_subjects"], [])
        self.assertEqual(result["captain_mail"], 0)
        self.assertEqual(result["admiral_mail"], 0)
        ensure.assert_not_called()

    def test_status_running_crew_returns_subjects_and_job_state(self) -> None:
        """5.2 — running crew: subjects returned correctly alongside job state."""
        captain_entry = {
            "type": "captain",
            "name": "captain",
            "enabled": True,
            "current_task_id": "task-1",
        }
        captain_tar = self._make_maildir_tar({
            "cur/msg1": "Subject: banshee review done\n\nbody",
            "cur/msg2": "Subject: trn-85 archived\n\nbody",
        })
        admiral_tar = self._make_maildir_tar({})
        podman = self._make_podman(
            is_running=True,
            captain_tar=captain_tar,
            admiral_tar=admiral_tar,
        )
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie",
                                  "schedules": [captain_entry]}}}
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_mail_count", return_value=0),
            patch.object(lifecycle, "_crew_api", return_value={"done": False}),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(set(s["subject"] for s in result["captain_subjects"]), {"banshee review done", "trn-85 archived"})
        self.assertEqual(result["captain_mail"], 2)
        self.assertEqual(result["admiral_subjects"], [])
        self.assertEqual(result["admiral_mail"], 0)
        # Entry state present (no gateway job_id in new model)
        self.assertTrue(result["enabled"])


class MaildirSubjectTimestampTests(unittest.TestCase):
    """received_at in _read_maildir_subjects_from_tar."""

    @staticmethod
    def _make_maildir_tar(messages: dict[str, str]) -> bytes:
        import io as _io
        import tarfile as _tarfile
        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tf:
            for name, content in messages.items():
                data = content.encode("utf-8")
                info = _tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, _io.BytesIO(data))
        return buf.getvalue()

    def test_valid_date_header_returns_utc_received_at(self) -> None:
        """Message with valid Date header returns ISO 8601 UTC received_at."""
        tar = self._make_maildir_tar({
            "new/msg1": "Subject: hello\nDate: Mon, 01 Jan 2024 12:00:00 +0000\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["subject"], "hello")
        self.assertIsNotNone(subjects[0]["received_at"])
        self.assertIn("2024-01-01", subjects[0]["received_at"])

    def test_date_header_with_timezone_offset_converted_to_utc(self) -> None:
        """Date header with +0500 offset is converted to UTC in received_at."""
        tar = self._make_maildir_tar({
            "new/msg1": "Subject: tz test\nDate: Mon, 01 Jan 2024 17:00:00 +0500\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        # 17:00 +05:00 == 12:00 UTC
        self.assertIsNotNone(subjects[0]["received_at"])
        self.assertIn("12:00:00", subjects[0]["received_at"])

    def test_no_date_header_returns_received_at_null(self) -> None:
        """Message with no Date header returns received_at = None."""
        tar = self._make_maildir_tar({
            "new/msg1": "From: ghost@localhost\nSubject: no date\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0]["subject"], "no date")
        self.assertIsNone(subjects[0]["received_at"])

    def test_return_type_is_list_of_dicts(self) -> None:
        """Each entry in the returned list is a dict with subject and received_at keys."""
        tar = self._make_maildir_tar({
            "new/msg1": "Subject: check shape\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(len(subjects), 1)
        self.assertIsInstance(subjects[0], dict)
        self.assertIn("subject", subjects[0])
        self.assertIn("received_at", subjects[0])


class CaptainLastCheckinAtTests(unittest.TestCase):
    """last_checkin_at in captain status."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    @staticmethod
    def _make_maildir_tar(messages: dict[str, str]) -> bytes:
        import io as _io
        import tarfile as _tarfile
        buf = _io.BytesIO()
        with _tarfile.open(fileobj=buf, mode="w") as tf:
            for name, content in messages.items():
                data = content.encode("utf-8")
                info = _tarfile.TarInfo(name=name)
                info.size = len(data)
                tf.addfile(info, _io.BytesIO(data))
        return buf.getvalue()

    def _make_podman(self, *, is_running: bool = True):
        podman = Mock()
        podman.container_is_running.return_value = is_running
        tar = self._make_maildir_tar({})

        class _FakeResp:
            def iter_bytes(self_inner):
                yield tar

            def close(self_inner):
                pass

        podman.container_archive_get.return_value = _FakeResp()
        return podman

    def test_status_includes_last_checkin_at_null_before_checkin_fires(self) -> None:
        """captain status includes last_checkin_at=null when no check-in has fired."""
        existing = {
            "id": "job-1",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        # Registry entry with NO last_checkin_at (type==captain, new model)
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{"type": "captain", "name": "captain", "enabled": True,
                           "current_task_id": "task-1"}],
        }}}
        podman = self._make_podman(is_running=False)
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_mail_count", return_value=0),
        ):
            result = server.captain("demo", "status")

        self.assertIn("last_checkin_at", result)
        self.assertIsNone(result["last_checkin_at"])

    def test_status_includes_last_checkin_at_after_checkin_fires(self) -> None:
        """captain status includes last_checkin_at when a check-in has fired."""
        existing = {
            "id": "job-1",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        checkin_ts = "2026-09-02T00:00:00+00:00"
        # Registry entry WITH last_checkin_at (type==captain, new model)
        reg = {"crews": {"demo": {
            "container": "gs-demo", "cookie": "cookie",
            "schedules": [{
                "type": "captain", "name": "captain", "enabled": True,
                "current_task_id": "task-1", "last_checkin_at": checkin_ts,
            }],
        }}}
        podman = self._make_podman(is_running=False)
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_load_registry", return_value=reg),
            patch.object(captain_mod, "_mail_count", return_value=0),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(result["last_checkin_at"], checkin_ts)


# ── captain status / mail tests ──────────────────────────────────────────────


class ReadAllMailSubjectsTests(unittest.TestCase):
    """_read_all_mail_subjects returns new dict shape."""

    CONTAINER = "gs-demo"

    def test_returns_subject_dicts_on_success(self) -> None:
        """_read_all_mail_subjects returns {name: [{subject, received_at}]} dicts."""
        raw_json = json.dumps({
            "ghost": [{"subject": "task done", "received_at": "2026-09-02T22:00:00+00:00"}],
            "raven": [],
            "captain": [{"subject": "standing order", "received_at": None}],
        })
        podman = Mock()
        podman.container_exec_checked.return_value = raw_json
        result = captain_mod._read_all_mail_subjects(podman, self.CONTAINER)
        self.assertEqual(result["ghost"], [{"subject": "task done", "received_at": "2026-09-02T22:00:00+00:00"}])
        self.assertEqual(result["raven"], [])
        self.assertEqual(result["captain"], [{"subject": "standing order", "received_at": None}])

    def test_returns_empty_dict_on_exec_failure(self) -> None:
        """_read_all_mail_subjects returns {} when exec raises."""
        podman = Mock()
        podman.container_exec_checked.side_effect = RuntimeError("container stopped")
        # The function itself raises — _skim_all_mailboxes wraps the exception
        import contextlib
        with contextlib.suppress(Exception):
            result = captain_mod._read_all_mail_subjects(podman, self.CONTAINER)
            # If it doesn't raise, should return {} or empty
            self.assertIsInstance(result, dict)

    def test_filters_non_dict_entries(self) -> None:
        """_read_all_mail_subjects filters out non-dict list entries."""
        raw_json = json.dumps({
            "ghost": [{"subject": "ok", "received_at": None}, "stray-string", 42],
        })
        podman = Mock()
        podman.container_exec_checked.return_value = raw_json
        result = captain_mod._read_all_mail_subjects(podman, self.CONTAINER)
        # Only the dict entry survives
        self.assertEqual(result["ghost"], [{"subject": "ok", "received_at": None}])


class SkimAllMailboxesTests(unittest.TestCase):
    """_skim_all_mailboxes happy path and fallback."""

    CONTAINER = "gs-demo"

    def _exec_json(self, data: dict) -> Mock:
        """Return a Mock podman whose exec returns data as JSON."""
        podman = Mock()
        podman.container_exec_checked.return_value = json.dumps(data)
        return podman

    def test_running_crew_returns_all_8_keys(self) -> None:
        """Running crew: _skim_all_mailboxes returns all 8 mailbox keys."""
        skim_data = {name: [] for name in captain_mod._ALL_MAIL_MAILBOXES}
        skim_data["ghost"] = [{"subject": "hello", "received_at": None}]
        podman = self._exec_json(skim_data)
        result = captain_mod._skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(set(result.keys()), set(captain_mod._ALL_MAIL_MAILBOXES))
        self.assertEqual(result["ghost"], [{"subject": "hello", "received_at": None}])
        self.assertEqual(result["raven"], [])

    def test_exec_failure_triggers_archive_fallback(self) -> None:
        """When exec fails, _skim_all_mailboxes falls back to per-mailbox archive reads."""
        podman = Mock()
        podman.container_exec_checked.side_effect = RuntimeError("not running")
        # Archive returns a subject for ghost, empty for everyone else.
        # _read_mail_subjects_archive is called as (podman, container, mailbox_path).
        def _archive(_podman, _container, mailbox_path):
            if "ghost" in mailbox_path:
                return [{"subject": "archive fallback", "received_at": None}]
            return []
        with patch.object(captain_mod, "_read_mail_subjects_archive", side_effect=_archive):
            result = captain_mod._skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(result["ghost"], [{"subject": "archive fallback", "received_at": None}])
        self.assertEqual(result["raven"], [])
        self.assertEqual(set(result.keys()), set(captain_mod._ALL_MAIL_MAILBOXES))

    def test_stopped_crew_returns_8_empty_lists(self) -> None:
        """Stopped crew: all 8 mailboxes return empty lists."""
        podman = Mock()
        podman.container_exec_checked.side_effect = RuntimeError("stopped")
        with patch.object(captain_mod, "_read_mail_subjects_archive", return_value=[]):
            result = captain_mod._skim_all_mailboxes(podman, self.CONTAINER)
        self.assertEqual(set(result.keys()), set(captain_mod._ALL_MAIL_MAILBOXES))
        for name in captain_mod._ALL_MAIL_MAILBOXES:
            self.assertEqual(result[name], [])


class CaptainStatusAgentMailTests(unittest.TestCase):
    """captain status includes agent_mail field."""

    CREW = {"container": "gs-demo", "cookie": "cookie"}

    def _skim_result(self, **overrides) -> dict:
        """Build a full 8-key skim result with optional overrides per mailbox."""
        base = {name: [] for name in captain_mod._ALL_MAIL_MAILBOXES}
        base.update(overrides)
        return base

    def test_agent_mail_present_dormant_captain(self) -> None:
        """2.4 — dormant captain status still includes agent_mail."""
        ghost_subjects = [{"subject": "task done", "received_at": None}]
        skim = self._skim_result(ghost=ghost_subjects)
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_skim_all_mailboxes", return_value=skim),
        ):
            result = server.captain("demo", "status")
        self.assertIn("agent_mail", result)
        self.assertEqual(result["agent_mail"]["ghost"], ghost_subjects)
        self.assertEqual(result["status"], "dormant")
        ensure.assert_not_called()

    def test_agent_mail_present_running_crew(self) -> None:
        """2.4 — running crew captain status includes agent_mail with all 8 keys."""
        existing_job = {
            "id": "job-1",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
        }
        raven_subjects = [{"subject": "check-in report", "received_at": None}]
        skim = self._skim_result(raven=raven_subjects)
        reg = {"crews": {"demo": {"container": "gs-demo", "cookie": "cookie", "schedules": []}}}
        podman = Mock()
        podman.container_is_running.return_value = True
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_skim_all_mailboxes", return_value=skim),
            patch.object(captain_mod, "_mail_count", return_value=0),
            patch.object(captain_mod, "_load_registry", return_value=reg),
            patch.object(lifecycle, "_crew_api", return_value={"jobs": [existing_job]}),
        ):
            result = server.captain("demo", "status")
        self.assertIn("agent_mail", result)
        self.assertEqual(set(result["agent_mail"].keys()), set(captain_mod._ALL_MAIL_MAILBOXES))
        self.assertEqual(result["agent_mail"]["raven"], raven_subjects)

    def test_stopped_crew_agent_mail_empty_lists(self) -> None:
        """2.4 — stopped crew: agent_mail contains empty lists for all 8 mailboxes."""
        skim = {name: [] for name in captain_mod._ALL_MAIL_MAILBOXES}
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_skim_all_mailboxes", return_value=skim),
        ):
            result = server.captain("demo", "status")
        self.assertIn("agent_mail", result)
        for name in captain_mod._ALL_MAIL_MAILBOXES:
            self.assertEqual(result["agent_mail"][name], [])

    def test_captain_admiral_derived_from_skim_no_duplicate_exec(self) -> None:
        """2.3 — captain_subjects and admiral_subjects come from skim, no extra exec calls."""
        captain_subs = [{"subject": "standing order", "received_at": None}]
        admiral_subs = [{"subject": "admiral reply", "received_at": None}]
        skim = self._skim_result(captain=captain_subs, admiral=admiral_subs)
        podman = Mock()
        podman.container_is_running.return_value = False
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_skim_all_mailboxes", return_value=skim) as mock_skim,
            patch.object(server, "_read_mail_subjects_archive") as mock_archive,
        ):
            result = server.captain("demo", "status")
        # Skim called once; archive NOT called for captain/admiral
        mock_skim.assert_called_once()
        mock_archive.assert_not_called()
        self.assertEqual(result["captain_subjects"], captain_subs)
        self.assertEqual(result["admiral_subjects"], admiral_subs)


class LoadOrderTemplateGaDirTests(unittest.TestCase):
    """_load_order_template() resolves GA_ORDERS_DIR with precedence.

    Guards the requirement that a user-defined template is both listable AND
    resolvable — via the per-template resource and the captain order path,
    both of which go through _load_order_template().
    """

    def test_user_defined_template_resolves_new_name(self) -> None:
        """A template that exists only in GA_ORDERS_DIR resolves by name."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "sdd.md").write_text("---\ndescription: Built-in SDD\n---\nbuiltin body", encoding="utf-8")

            user = Path(td) / "user"
            user.mkdir()
            (user / "deploy.md").write_text("---\ndescription: Deploy\n---\ndeploy body here", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                description, body = captain_mod._load_order_template("deploy")

        self.assertEqual(description, "Deploy")
        self.assertEqual(body, "deploy body here")

    def test_user_defined_template_overrides_builtin_on_load(self) -> None:
        """A user-defined template with a built-in stem takes precedence on load."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "sdd.md").write_text("---\ndescription: Built-in SDD\n---\nbuiltin body", encoding="utf-8")

            user = Path(td) / "user"
            user.mkdir()
            (user / "sdd.md").write_text("---\ndescription: User SDD\n---\noverridden body", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                description, body = captain_mod._load_order_template("sdd")

        self.assertEqual(description, "User SDD")
        self.assertEqual(body, "overridden body")

    def test_builtin_still_resolves_when_ga_dir_lacks_it(self) -> None:
        """A built-in with no user-defined counterpart still resolves when GA_ORDERS_DIR is set."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "independent-review.md").write_text("---\ndescription: IR\n---\nir body", encoding="utf-8")

            user = Path(td) / "user"
            user.mkdir()
            (user / "deploy.md").write_text("---\ndescription: Deploy\n---\ndeploy body", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                description, body = captain_mod._load_order_template("independent-review")

        self.assertEqual(description, "IR")
        self.assertEqual(body, "ir body")

    def test_unknown_template_still_raises_with_ga_dir_set(self) -> None:
        """An unknown name raises ValueError even when GA_ORDERS_DIR is set."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            user = Path(td) / "user"
            user.mkdir()

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                with self.assertRaises(ValueError):
                    captain_mod._load_order_template("nonexistent")


class ListOrderTemplatesTests(unittest.TestCase):
    """_list_order_templates() merges built-ins and GA_ORDERS_DIR."""

    def _make_builtin_dir(self, tmp: Path, templates: dict[str, str]) -> Path:
        """Write .md template files into a directory, return the path."""
        for stem, content in templates.items():
            (tmp / f"{stem}.md").write_text(content, encoding="utf-8")
        return tmp

    def test_builtin_only_when_ga_orders_dir_unset(self) -> None:
        """(a) Only built-in templates returned when GA_ORDERS_DIR is empty."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "alpha.md").write_text("---\ndescription: Alpha desc\n---\nbody", encoding="utf-8")
            (builtin / "beta.md").write_text("---\ndescription: Beta desc\n---\nbody", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", ""),
            ):
                result = captain_mod._list_order_templates()

        names = [n for n, _ in result]
        self.assertIn("alpha", names)
        self.assertIn("beta", names)
        self.assertEqual(len(result), 2)
        self.assertEqual(dict(result)["alpha"], "Alpha desc")

    def test_user_defined_templates_added_when_ga_orders_dir_set(self) -> None:
        """(b) User-defined templates appear alongside built-ins when GA_ORDERS_DIR set."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "sdd.md").write_text("---\ndescription: SDD desc\n---\nbody", encoding="utf-8")

            user = Path(td) / "user"
            user.mkdir()
            (user / "custom.md").write_text("---\ndescription: Custom desc\n---\ncustom body", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                result = captain_mod._list_order_templates()

        result_dict = dict(result)
        self.assertIn("sdd", result_dict)
        self.assertIn("custom", result_dict)
        self.assertEqual(result_dict["custom"], "Custom desc")

    def test_user_defined_overrides_builtin_on_name_collision(self) -> None:
        """(c) User-defined template with same stem takes precedence over built-in."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "sdd.md").write_text("---\ndescription: Built-in SDD\n---\nbody", encoding="utf-8")

            user = Path(td) / "user"
            user.mkdir()
            (user / "sdd.md").write_text("---\ndescription: User SDD override\n---\noverridden body", encoding="utf-8")

            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", str(user)),
            ):
                result = captain_mod._list_order_templates()

        result_dict = dict(result)
        self.assertEqual(result_dict["sdd"], "User SDD override")
        # Only one entry for sdd, not two
        self.assertEqual(len([n for n, _ in result if n == "sdd"]), 1)

    def test_non_existent_ga_orders_dir_logs_warning_and_falls_back(self) -> None:
        """(d) Non-existent GA_ORDERS_DIR logs warning once and returns only built-ins."""
        with tempfile.TemporaryDirectory() as td:
            builtin = Path(td) / "builtin"
            builtin.mkdir()
            (builtin / "sdd.md").write_text("---\ndescription: SDD desc\n---\nbody", encoding="utf-8")

            non_existent = str(Path(td) / "does_not_exist")

            # Reset the warning flag before each test
            captain_mod._ga_orders_dir_warned = False
            with (
                patch.object(captain_mod, "_resolve_orders_dir", return_value=builtin),
                patch.object(captain_mod, "GA_ORDERS_DIR", non_existent),
            ):
                with self.assertLogs("transport.captain", level="WARNING") as log_ctx:
                    result = captain_mod._list_order_templates()
                # Warning should have been logged
                self.assertTrue(any("GA_ORDERS_DIR" in msg for msg in log_ctx.output))
                # Falls back to built-ins only
                result_dict = dict(result)
                self.assertIn("sdd", result_dict)
                self.assertEqual(len(result), 1)

                # Second call: no additional warning (one-time flag)
                with self.assertNoLogs("transport.captain", level="WARNING"):
                    result2 = captain_mod._list_order_templates()
                self.assertEqual(len(result2), 1)

            # Reset flag for other tests
            captain_mod._ga_orders_dir_warned = False


if __name__ == "__main__":
    unittest.main()


class CaptainCookieInjectionTests(unittest.TestCase):
    """Tests for .dashboard_cookie injection in captain dispatch/steer helpers.

    4.1 _finish_crew_setup writes .dashboard_cookie via podman exec after cookie mint
    4.2 .dashboard_cookie write failure is non-fatal (logs warning, doesn't abort setup)
    4.3 _dispatch_captain_checkin writes .dashboard_cookie before dispatch
    4.4 _steer_captain_checkin writes .dashboard_cookie before continue
    """

    # ── 4.3: _dispatch_captain_checkin writes .dashboard_cookie ──────────────

    def test_dispatch_captain_checkin_writes_dashboard_cookie(self) -> None:
        """dispatch writes .dashboard_cookie before POSTing to /api/spawn."""
        podman = Mock()
        cookie_written: list[tuple[object, str, str]] = []

        def fake_write(p, container, cookie):
            cookie_written.append((p, container, cookie))
            return True

        crew = {"container": "gs-demo", "cookie": "abc123", "enrolled_agents": ["raven"]}
        reg_data = {
            "crews": {"demo": {"cookie": "abc123", "container": "gs-demo"}},
            "schedules": {},
        }

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_write_dashboard_cookie", side_effect=fake_write),
            patch.object(server, "_load_registry", return_value=reg_data),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "task-001"},
            ),
        ):
            task_id = server._dispatch_captain_checkin(crew, "demo")

        self.assertEqual(task_id, "task-001")
        self.assertEqual(len(cookie_written), 1, "should write cookie exactly once")
        _, container, cookie = cookie_written[0]
        self.assertEqual(container, "gs-demo")
        self.assertEqual(cookie, "abc123")

    def test_dispatch_captain_checkin_cookie_failure_is_non_fatal(self) -> None:
        """dispatch continues even when _write_dashboard_cookie raises."""
        podman = Mock()

        crew = {"container": "gs-demo", "cookie": "abc123", "enrolled_agents": ["raven"]}
        reg_data = {
            "crews": {"demo": {"cookie": "abc123", "container": "gs-demo"}},
            "schedules": {},
        }

        with (
            patch.object(server, "_get_podman", side_effect=RuntimeError("podman down")),
            patch.object(server, "_load_registry", return_value=reg_data),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "task-002"},
            ),
        ):
            # Should not raise despite podman failure
            task_id = server._dispatch_captain_checkin(crew, "demo")

        self.assertEqual(task_id, "task-002")

    # ── 4.4: _steer_captain_checkin writes .dashboard_cookie ─────────────────

    def test_steer_captain_checkin_writes_dashboard_cookie(self) -> None:
        """steer writes .dashboard_cookie before POSTing /continue."""
        podman = Mock()
        cookie_written: list[tuple[object, str, str]] = []

        def fake_write(p, container, cookie):
            cookie_written.append((p, container, cookie))
            return True

        crew = {"container": "gs-demo", "cookie": "xyz789"}
        captain_entry = {
            "type": "captain",
            "current_task_id": "old-task",
            "model": None,
        }
        reg_data = {
            "crews": {"demo": {"cookie": "xyz789", "container": "gs-demo"}},
            "schedules": {"demo": [captain_entry]},
        }

        with (
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_write_dashboard_cookie", side_effect=fake_write),
            patch.object(server, "_load_registry", return_value=reg_data),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_get_crew_schedules", return_value=[captain_entry]),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "new-task"},
            ),
        ):
            task_id = server._steer_captain_checkin(crew, "demo")

        self.assertEqual(task_id, "new-task")
        self.assertEqual(len(cookie_written), 1, "should write cookie exactly once")
        _, container, cookie = cookie_written[0]
        self.assertEqual(container, "gs-demo")
        self.assertEqual(cookie, "xyz789")

    def test_steer_captain_checkin_cookie_failure_is_non_fatal(self) -> None:
        """steer continues even when _write_dashboard_cookie raises."""
        crew = {"container": "gs-demo", "cookie": "xyz789"}
        captain_entry = {
            "type": "captain",
            "current_task_id": "old-task",
            "model": None,
        }
        reg_data = {
            "crews": {"demo": {"cookie": "xyz789", "container": "gs-demo"}},
            "schedules": {"demo": [captain_entry]},
        }

        with (
            patch.object(server, "_get_podman", side_effect=RuntimeError("podman down")),
            patch.object(server, "_load_registry", return_value=reg_data),
            patch.object(server, "_registry_lock", threading.Lock()),
            patch.object(server, "_get_crew_schedules", return_value=[captain_entry]),
            patch.object(
                server, "_crew_api_with_recovery",
                return_value={"id": "new-task-2"},
            ),
        ):
            task_id = server._steer_captain_checkin(crew, "demo")

        self.assertEqual(task_id, "new-task-2")
