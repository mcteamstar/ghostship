# ── Test suite portability (trn-17) ───────────────────────────────────────────
#
# Podman-dependent test classes/methods (require a real `podman` binary or a
# live Podman socket) are guarded with
#   @unittest.skipUnless(shutil.which("podman"), "requires podman")
# and/or @unittest.skipUnless(shutil.which("git"), ...) for git-backed cases.
# The remainder are pure unit tests that mock PodmanClient and run to
# completion in any environment — including inside a crew container that has
# no podman socket.
#
# Podman/git-dependent (auto-skip when the binary is absent):
#   FileGetRegressionTests            — @skipUnless(git) per-method
#   BundleGetRegressionTests          — @skipUnless(git) per-method
#   BundleHardeningTests              — @skipUnless(git) on the archive test
#
# Portable (pure unit tests, always run — mock PodmanClient, no socket):
#   BundleUploadToolTests, FileUrlBaseResolutionTests, LifecycleRegressionTests,
#   NukeScheduleTests, PickupTimeoutTests, PersonaValidationTests, TaskOrchestrationTests,
#   IdleMonitorActivityTests, CaptainStandingOrdersTests, FireImmediatelyTests,
#   GatewayTokenAndProjectionTests, BearerAuthMiddlewareTests, StartupWiringTests,
#   LoginLogoutTests, TestCrewTypeRegistry, TestCrewTypeHelpers, TestLaunchCrewType,
#   TestCrewTypesTool, ScheduleCancelTests, ScheduleCreateValidationTests,
#   ScheduleListTests, DispatchFireAfterTests, ResourceJobsTests, TestPolicyInjection,
#   TestMemoryGate, TestPatchCrewConfig, TestCrewsMemoryField, TestMemoryCache,
#   ReconcileRegistryTests, IdleMonitorTests, FinishCrewSetupOrderingTests,
#   LoginFlowEdgeCaseTests, LoginGuardClearTests  (trn-17 additions)
#   ActiveCrewLimitTests  (trn-40 additions)
#   NukeScheduleTests  (trn-59 additions)
#   ReadAuthFromCrewTests  (trn-78 additions)


#   ScheduleMonitorTests, SchedulePersistenceTests  (trn-39 additions)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import base64
import os
import stat
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch

from tests.unit.test_file_transfer import server
import transport.academy as academy
import transport.lifecycle as lifecycle

import httpx
import transport.registry as _registry_mod
import transport.podman as _podman_mod
import transport.files as _files_mod
import transport.captain as _captain_mod

# TRN-85: FakePodmanClient moved to tests/unit/helpers.py during the podman
# migration; still used by not-yet-migrated classes in this file (e.g.
# ActiveCrewLimitTests → test_lifecycle.py). This import disappears once those
# classes migrate.
from tests.unit.helpers import FakePodmanClient, Request  # noqa: E402

# ── container_scripts import (TRN-74) ────────────────────────────────────────
# _inject_policy / _patch_crew_config now invoke baked scripts under
# transport/container_scripts/ instead of inline `python3 -c` strings. Import
# the policy signer directly so policy-injection tests can run the SAME code
# the container runs, decoding the base64 payload from the captured argv.
import importlib as _importlib

_CONTAINER_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2] / "transport" / "container_scripts"
)
if str(_CONTAINER_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTAINER_SCRIPTS_DIR))
_inject_policy_script = _importlib.import_module("inject_policy")



if __name__ == "__main__":
    import unittest
    unittest.main()
