"""TRN-191 — WebSocket 403: gateway allowed-origins must include the crew's
own container hostname.

Covers:
- 3.1 ``_patch_crew_config`` writes ``dashboard.url`` ==
      ``http://gs-{crew_id}:{CREW_GATEWAY_PORT}`` (exact string match) into the
      config.local.json patch, so the gateway's startup-built ``allowed_origins``
      set includes the internal container origin the transport WS proxy injects
      as its handshake ``Origin``. Without it the gateway falls back to
      loopback-only and rejects the proxied upgrade with
      ``403 WebSocket origin not allowed``.

The value must be byte-identical to the ``Origin`` the proxy sends
(``server.py``: ``http://{CREW_CONTAINER_PREFIX}{crew_id}:{CREW_GATEWAY_PORT}``) —
any scheme/port/host drift re-triggers the 403, so the test pins the exact
string rather than a substring.
"""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import Mock

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
from tests.unit._stubs import install_import_stubs

install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402
from transport.constants import (  # noqa: E402
    CREW_CONTAINER_PREFIX,
    CREW_GATEWAY_PORT,
)


# ── 3.1 _patch_crew_config writes dashboard.url == the container origin ───────


class TestPatchCrewConfigDashboardUrl(unittest.TestCase):
    def _run_patch(self, container: str) -> dict:
        """Invoke _patch_crew_config and return the decoded overrides dict
        handed to patch_crew_config.py."""
        podman = Mock()
        captured: list[str] = []

        def capture_exec(container_name, cmd, **kwargs):
            if len(cmd) >= 4 and "patch_crew_config.py" in cmd[1]:
                captured.append(cmd[3])
            return "patched config.local.json"

        podman.container_exec.side_effect = capture_exec

        _lifecycle._patch_crew_config(podman, container)

        self.assertEqual(len(captured), 1, "expected exactly one config patch exec")
        return json.loads(base64.b64decode(captured[0]).decode())

    def test_dashboard_url_set_to_container_origin(self) -> None:
        crew_id = "alpha"
        container = f"{CREW_CONTAINER_PREFIX}{crew_id}"
        overrides = self._run_patch(container)

        self.assertIn("dashboard", overrides, "overrides must carry a dashboard section")
        self.assertEqual(
            overrides["dashboard"].get("url"),
            f"http://{container}:{CREW_GATEWAY_PORT}",
        )

    def test_dashboard_url_matches_proxy_injected_origin_exactly(self) -> None:
        """The value must equal the Origin the WS proxy injects — the canonical
        example from the spec, http://gs-alpha:5476."""
        crew_id = "alpha"
        container = f"{CREW_CONTAINER_PREFIX}{crew_id}"
        overrides = self._run_patch(container)

        self.assertEqual(overrides["dashboard"]["url"], "http://gs-alpha:5476")

    def test_dashboard_url_composed_from_container_arg_not_literals(self) -> None:
        """A different crew_id yields a different, correctly-composed origin —
        guards against a hard-coded hostname regressing the fix."""
        container = f"{CREW_CONTAINER_PREFIX}crew-xyz-123"
        overrides = self._run_patch(container)

        self.assertEqual(
            overrides["dashboard"]["url"],
            f"http://{container}:{CREW_GATEWAY_PORT}",
        )


if __name__ == "__main__":
    unittest.main()
