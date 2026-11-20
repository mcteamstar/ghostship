"""Unit tests for transport/kiro_signin.py — transport-side kiro sign-in checks."""
from __future__ import annotations

import base64
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import transport.kiro_signin as ks
import transport.lifecycle as lc


def _payload(with_profile: bool) -> bytes:
    state = [["api.codewhisperer.profile", json.dumps({"arn": "arn:x", "profile_name": "P"})]] if with_profile else []
    return base64.b64encode(json.dumps({"v": 2, "auth_kv": [["kirocli:odic:token", "t"]], "state": state}).encode())


class _FakeRegistry:
    def __init__(self, crews: dict):
        self._reg = {"crews": crews}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeStore:
    def __init__(self, cred):
        self.cred = cred

    def get(self, backend, profile="default"):
        return self.cred


class _Base(unittest.TestCase):
    def setUp(self):
        self.crews = {"k1": {"container": "gs-k1", "acp_backend": "kiro", "acp_profile": "default"}}
        self.store = _FakeStore({"method": "identity-center", "payload": _payload(True)})
        self.prereq = {"authenticated": True, "ready": True}
        self.api_calls = 0

        def fake_api(crew, method, path, **kw):
            self.api_calls += 1
            if isinstance(self.prereq, Exception):
                raise self.prereq
            return self.prereq

        for name, value in (
            ("registry", _FakeRegistry(self.crews)),
            ("_cred_store", self.store),
            ("_crew_api", fake_api),
        ):
            p = patch.object(lc, name, value)
            p.start()
            self.addCleanup(p.stop)

    def crew(self):
        return dict(self.crews["k1"])


class TestEvaluate(_Base):
    def test_ok_when_profile_and_gateway_authenticated(self):
        self.assertTrue(ks.evaluate("k1", self.crew())["ok"])

    def test_idc_credential_without_profile_not_ok_without_asking_gateway(self):
        self.store.cred = {"method": "identity-center", "payload": _payload(False)}
        state = ks.evaluate("k1", self.crew())
        self.assertIs(state["ok"], False)
        self.assertIn("no Kiro profile", state["reason"])
        self.assertEqual(self.api_calls, 0)

    def test_builder_id_needs_no_profile(self):
        self.store.cred = {"method": "builder-id", "payload": _payload(False)}
        self.assertTrue(ks.evaluate("k1", self.crew())["ok"])

    def test_missing_credential_not_ok(self):
        self.store.cred = None
        self.assertIs(ks.evaluate("k1", self.crew())["ok"], False)

    def test_gateway_signed_out_not_ok(self):
        self.prereq = {"authenticated": False}
        state = ks.evaluate("k1", self.crew())
        self.assertIs(state["ok"], False)
        self.assertIn("not signed in", state["reason"])

    def test_gateway_unreachable_is_unknown(self):
        self.prereq = RuntimeError("connection refused")
        self.assertIsNone(ks.evaluate("k1", self.crew())["ok"])


class TestDispatchGuard(_Base):
    def test_unknown_state_proceeds_without_probe(self):
        self.assertIsNone(ks.dispatch_guard("k1", self.crew()))
        self.assertEqual(self.api_calls, 0)

    def test_non_kiro_crew_ignored(self):
        self.crews["k1"]["acp_backend"] = "claude"
        self.crews["k1"]["kiro_signin"] = {"ok": False, "reason": "x",
                                           "checked_at": datetime.now(timezone.utc).isoformat()}
        self.assertIsNone(ks.dispatch_guard("k1", self.crew()))

    def test_fresh_signed_out_record_refuses(self):
        self.crews["k1"]["kiro_signin"] = {"ok": False, "reason": "kiro-cli in the crew is not signed in",
                                           "checked_at": datetime.now(timezone.utc).isoformat()}
        denied = ks.dispatch_guard("k1", self.crew())
        self.assertEqual(denied["error"], "not_authenticated")
        self.assertIn("ghostship auth login kiro", denied["message"])
        self.assertEqual(self.api_calls, 0)

    def test_stale_signed_out_record_rechecked_and_recovers(self):
        old = (datetime.now(timezone.utc) - timedelta(seconds=ks.RECHECK_SECS + 5)).isoformat()
        self.crews["k1"]["kiro_signin"] = {"ok": False, "reason": "old", "checked_at": old}
        self.assertIsNone(ks.dispatch_guard("k1", self.crew()))
        self.assertTrue(self.crews["k1"]["kiro_signin"]["ok"])

    def test_clear_removes_record(self):
        self.crews["k1"]["kiro_signin"] = {"ok": False, "reason": "x", "checked_at": "2026-01-01T00:00:00+00:00"}
        ks.clear("k1")
        self.assertNotIn("kiro_signin", self.crews["k1"])


class TestExplainFailure(_Base):
    NO_PROFILE = ("kiro_crew.acp.client.AcpError: Prompt error: {'code': -32000, 'message': "
                  "'Auth refresh callback failed: Internal error: No profile selected.'}")
    MCP_TIMEOUT = "KAS managed MCP readiness timed out after 90s: kirocrew-cron: unreported"

    def test_confirmed_signin_failure_rewritten(self):
        self.prereq = {"authenticated": False}
        out = ks.explain_failure("k1", self.crew(), self.MCP_TIMEOUT)
        self.assertEqual(out["error_code"], "not_authenticated")
        self.assertEqual(out["upstream_error"], self.MCP_TIMEOUT)
        self.assertIn("not signed in", out["error"])
        self.assertIs(self.crews["k1"]["kiro_signin"]["ok"], False)

    def test_marker_but_signin_ok_leaves_error(self):
        self.assertIsNone(ks.explain_failure("k1", self.crew(), self.MCP_TIMEOUT))

    def test_unrelated_error_never_probes(self):
        self.assertIsNone(ks.explain_failure("k1", self.crew(), "rate_limit"))
        self.assertEqual(self.api_calls, 0)

    def test_profile_less_credential_explained(self):
        self.store.cred = {"method": "identity-center", "payload": _payload(False)}
        out = ks.explain_failure("k1", self.crew(), self.NO_PROFILE)
        self.assertIn("no Kiro profile", out["error"])

    def test_list_view_uses_recorded_state_only(self):
        self.prereq = {"authenticated": False}
        self.assertIsNone(ks.explain_failure("k1", self.crew(), self.MCP_TIMEOUT, probe=False))
        self.assertEqual(self.api_calls, 0)
        self.crews["k1"]["kiro_signin"] = {"ok": False, "reason": "kiro-cli in the crew is not signed in",
                                           "checked_at": datetime.now(timezone.utc).isoformat()}
        out = ks.explain_failure("k1", self.crew(), self.MCP_TIMEOUT, probe=False)
        self.assertEqual(out["error_code"], "not_authenticated")
        self.assertEqual(self.api_calls, 0)


if __name__ == "__main__":
    unittest.main()
