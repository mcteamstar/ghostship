"""Unit tests for ``transport.captain`` — Captain standing orders + mail helpers.

TRN-85 migration target. ``CaptainStandingOrdersTests`` exercises the
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
  dual-patch shadows from TRN-71 are dropped).
"""

from __future__ import annotations

import base64
import json
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
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(server, "_append_captain_mail") as append,
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}, {"id": "immediate"}],) as api,
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
            patch.object(lifecycle, "_crew_api", side_effect=api),
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
        definition_path = Path(__file__).resolve().parents[2] / "academy" / "agents" / "raven.json"
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
        definition_path = Path(__file__).resolve().parents[2] / "academy" / "agents" / "raven.json"
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
        definition_path = Path(__file__).resolve().parents[2] / "academy" / "agents" / "raven.json"
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
            patch.object(lifecycle, "_crew_api", return_value={"jobs": []}) as api,
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
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}],) as api,
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
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": []}, {"id": "job-1", "enabled": True}],) as api,
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
            patch.object(lifecycle, "_crew_api", return_value={"jobs": [existing]}) as api,
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
            patch.object(captain_mod, "_mail_count", return_value=2),
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": [existing]}, {"ok": True}],) as api,
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
        """X-Admiral-Sig covers Subject, From, and body after parsing.

        Simulates the verify-admiral-sig logic: parse the message with
        email.message_from_string, extract the signed headers, strip the
        trailing newline from the payload, re-derive the HMAC, and compare.
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
        subject = msg.get("Subject", "")
        sender = msg.get("From", "")
        parsed_body = (msg.get_payload() or "").rstrip("\n")

        # Re-derive expected HMAC over the same headers and body as the verifier.
        expected = _hmac.new(
            secret.encode("utf-8"),
            f"Subject:{subject}\nFrom:{sender}\n\n{parsed_body}".encode("utf-8"),
            _hashlib.sha256,
        ).hexdigest()

        self.assertEqual(sig_header, expected, "X-Admiral-Sig should verify after stripping trailing newline")

    def test_mail_append_delivers_via_maildeliver(self) -> None:
        podman = Mock()
        server._append_captain_mail(podman, "gs-demo", "first order")
        command = podman.container_exec_checked.call_args.args[1]
        # Now invokes the baked-in script by path, with the message as a
        # base64 argv arg (no inline -c script, no shell-quoting hazard).
        self.assertEqual(command[0], "python3")
        self.assertTrue(command[1].endswith("/append_captain_mail.py"))
        decoded = base64.b64decode(command[2]).decode()
        # The delivered RFC822 message carries the captain order body.
        self.assertIn("first order", decoded)

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
            patch.object(captain_mod, "_mail_count", side_effect=[3, 2]) as mail_count,
            patch.object(lifecycle, "_crew_api", return_value={"jobs": [existing]}),
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
            patch.object(lifecycle, "_crew_api", return_value={"id": "job"}) as api,
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
            patch.object(lifecycle, "_crew_api") as api,
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
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": [existing]}, {"ok": True}],) as api,
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
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": [existing]}, {"ok": False}],),
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
            patch.object(captain_mod, "_mail_count", return_value=1),
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": [existing]}, {"ok": False}],),
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
            patch.object(captain_mod, "_mail_count", return_value=1),
 patch.object(lifecycle, "_crew_api", side_effect=[{"jobs": [existing]}, {"ok": True}],) as api,
        ):
            result = server.captain("demo", "stop")

        self.assertEqual(result["status"], "stopped")
        self.assertIs(api.call_args_list[1].args[0], refreshed)

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
        self.assertIn("task A done", subjects)
        self.assertIn("task B ready", subjects)
        self.assertEqual(len(subjects), 2)

    def test_ignores_files_outside_new_and_cur(self) -> None:
        tar = self._make_maildir_tar({
            "tmp/msg1": "Subject: should be ignored\n\nbody",
            "new/msg2": "Subject: included\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(subjects, ["included"])

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
        self.assertEqual(subjects, ["bytes path"])

    def test_deeply_nested_new_dir_is_included(self) -> None:
        """A path like captain/new/msg1 (tar from archive API) should be matched."""
        tar = self._make_maildir_tar({
            "captain/new/msg1": "Subject: deep subject\n\nbody",
        })
        subjects = captain_mod._read_maildir_subjects_from_tar(tar)
        self.assertEqual(subjects, ["deep subject"])

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
        self.assertEqual(result, ["order received"])

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
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running") as ensure,
            patch.object(server, "_get_podman", return_value=podman),
        ):
            result = server.captain("demo", "status")

        # Subjects are present
        self.assertEqual(result["captain_subjects"], ["trn-51 cleanup done"])
        self.assertEqual(result["admiral_subjects"], ["SO1 complete"])
        self.assertEqual(result["captain_mail"], 1)
        self.assertEqual(result["admiral_mail"], 1)
        # Status is dormant (no job found on a stopped container)
        self.assertEqual(result["status"], "dormant")
        # Container was NOT started
        ensure.assert_not_called()
        podman.container_is_running.assert_called_once()

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
        existing = {
            "id": "job-existing",
            "name": server._CAPTAIN_CHECKIN_JOB_NAME,
            "agent": "raven",
            "enabled": True,
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
        with (
            patch.object(server, "_require_crew", return_value=self.CREW),
            patch.object(server, "_ensure_crew_running", return_value=self.CREW),
            patch.object(server, "_get_podman", return_value=podman),
            patch.object(captain_mod, "_mail_count", return_value=0),
            patch.object(lifecycle, "_crew_api", return_value={"jobs": [existing]}),
        ):
            result = server.captain("demo", "status")

        self.assertEqual(set(result["captain_subjects"]), {"banshee review done", "trn-85 archived"})
        self.assertEqual(result["captain_mail"], 2)
        self.assertEqual(result["admiral_subjects"], [])
        self.assertEqual(result["admiral_mail"], 0)
        # Job state still present
        self.assertEqual(result["job_id"], "job-existing")
        self.assertTrue(result["enabled"])


if __name__ == "__main__":
    unittest.main()
