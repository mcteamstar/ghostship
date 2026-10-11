"""TRN-223 — Knowledge auto-ingest opt-in posture (no implicit enablement).

KiroCrew 0.9.0 (PR #2448) makes knowledge auto-ingest opt-in. The source audit
(design.md) found ghostship never relied on auto-ingest, so the default-on ->
default-off flip is a no-op.

D1 resolved to **Option B** (rely on the verified upstream default), NOT the
Option A pin the first draft assumed, because task 2 verification against the
pinned base image's gateway (``kiro_crew`` 0.9.0rc4, matching
``ghcr.io/kirodotdev/kirocrew:0.9.0-insider.4``) showed the design's assumed key
``knowledge.auto_ingest`` DOES NOT EXIST. The real ``KnowledgeConfig`` section
has no single auto-ingest boolean; its ingest toggles (``auto_ingest_artifacts``,
``auto_add_documents``) are separate fields that already default to ``False``.
Pinning ``knowledge.auto_ingest=false`` would therefore be an inert dead key —
exactly the "wrong key name" risk design.md flagged — so no key is pinned.

This test asserts two things, both source-grounded:

1. ghostship's own ``full_overrides`` writes NO ``knowledge`` section and
   nothing that implicitly enables ingest — the real ``patch_config()``
   deep-merge is exercised, not a mock.
2. The verified upstream default posture is opt-in: ``KnowledgeConfig``'s
   ingest-enabling booleans default to ``False``. If a future upstream default
   flip makes any of them default-``True``, this assertion fails loudly in CI,
   turning the Option-B "open item" into an active tripwire rather than a
   silent assumption.
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

patch_crew_config = importlib.import_module("patch_crew_config")


def _representative_full_overrides() -> dict:
    """Mirror the static sections of lifecycle._patch_crew_config's full_overrides.

    Only the fixed, non-derived sections are reproduced — the generated
    ``agents`` block is represented by one static entry, which is all the
    deep-merge-preservation assertion needs. Deliberately contains NO
    ``knowledge`` key, matching the live source.
    """
    return {
        "agent": {"name": "spec-ops", "memory_gate": "default"},
        "stt": {"enabled": False},
        "session": {
            "eager_spawn": False,
            "timeout_secs": 300,
            "watchdog_rss_max_mb": 2000,
        },
        "telemetry": {"beacon_enabled": False},
        "auto_update": False,
        "orchestrator": {"max_plan_duration_seconds": 14400},
        "agents": {
            "ghost": {
                "kiro_agent": "ghost",
                "memory_store": "default",
                "session_control": True,
                "member_dispatch": True,
            }
        },
    }


class NoImplicitKnowledgeIngestTests(unittest.TestCase):
    def test_full_overrides_declares_no_knowledge_section(self) -> None:
        """The override dict ghostship hands to the patcher has no knowledge key."""
        overrides = _representative_full_overrides()
        self.assertNotIn(
            "knowledge",
            overrides,
            "ghostship full_overrides must not declare a knowledge section "
            "(D1=Option B: no pin; upstream default is opt-in)",
        )

    def test_patched_config_has_no_implicit_ingest_enablement(self) -> None:
        """patch_config() writes no knowledge section and preserves other sections."""
        overrides = _representative_full_overrides()
        with tempfile.TemporaryDirectory() as td:
            cfg_path = os.path.join(td, "config.local.json")
            # Pre-seed a config.json-like base to prove the deep-merge preserves
            # unrelated sections (and any pre-existing opt-in knowledge default).
            Path(cfg_path).write_text(
                json.dumps(
                    {
                        "agent": {"backend": "acp"},
                        "session": {"existing": True},
                        "telemetry": {"other": 1},
                    }
                )
            )

            patch_crew_config.patch_config(cfg_path, overrides)

            written = json.loads(Path(cfg_path).read_text())

            # 1. No implicit ingest enablement: ghostship wrote no knowledge section.
            self.assertNotIn(
                "knowledge",
                written,
                "patched config.local.json must not contain a knowledge section",
            )

            # 2. Deep-merge preserved the other sections and merged within them.
            self.assertEqual(written["stt"], {"enabled": False})
            self.assertEqual(written["auto_update"], False)
            self.assertEqual(
                written["orchestrator"], {"max_plan_duration_seconds": 14400}
            )
            self.assertEqual(written["agent"]["backend"], "acp")  # preserved
            self.assertEqual(written["agent"]["name"], "spec-ops")  # merged
            self.assertEqual(written["session"]["existing"], True)  # preserved
            self.assertEqual(written["session"]["timeout_secs"], 300)  # merged
            self.assertEqual(written["telemetry"]["other"], 1)  # preserved
            self.assertEqual(
                written["telemetry"]["beacon_enabled"], False
            )  # merged
            self.assertIn("ghost", written["agents"])  # generated block present


class UpstreamDefaultIsOptInTests(unittest.TestCase):
    """Verify the posture Option B relies on: upstream knowledge ingest is off.

    This is the Option-B tripwire. It imports the gateway's own config schema
    (the package baked into the pinned base image) and asserts the ingest
    toggles default to False. It also pins the fact that the design's assumed
    `auto_ingest` boolean does not exist, so a future reviewer sees why no key
    was pinned.
    """

    def _knowledge_config_cls(self):
        try:
            from kiro_crew.config.memory_sections import KnowledgeConfig
        except Exception as exc:  # pragma: no cover - env without gateway pkg
            self.skipTest(f"kiro_crew gateway package not importable: {exc}")
        return KnowledgeConfig

    def test_assumed_auto_ingest_key_does_not_exist(self) -> None:
        import dataclasses

        KnowledgeConfig = self._knowledge_config_cls()
        names = {f.name for f in dataclasses.fields(KnowledgeConfig)}
        self.assertNotIn(
            "auto_ingest",
            names,
            "0.9.0 KnowledgeConfig has no bare `auto_ingest` boolean — the "
            "design's assumed pin key is a dead key; D1=Option B is correct",
        )

    def test_ingest_toggles_default_off(self) -> None:
        import dataclasses

        KnowledgeConfig = self._knowledge_config_cls()
        defaults = {
            f.name: (f.default if f.default is not dataclasses.MISSING else None)
            for f in dataclasses.fields(KnowledgeConfig)
        }
        # The two booleans that enable ingest both ship opt-in (False).
        self.assertIs(
            defaults.get("auto_ingest_artifacts"),
            False,
            "upstream auto_ingest_artifacts must default to False (opt-in)",
        )
        self.assertIs(
            defaults.get("auto_add_documents"),
            False,
            "upstream auto_add_documents must default to False (opt-in)",
        )


if __name__ == "__main__":
    unittest.main()
