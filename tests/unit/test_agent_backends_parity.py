"""Parity between the Python and shell GA_AGENT_BACKENDS parsers (TRN-202).

transport/config.py (parse_agent_backends) and scripts/lib/agent_backends.sh
(agent_backends_normalise) must agree, because install.sh builds the image from
one and the transport validates against the other. These tests source the real
shell file rather than copying its logic.

Also checks that the transport's optional backends match the toolchain scripts
under crews/spec-ops/toolchains/, so neither side can know a backend the other
doesn't.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.unit._stubs import install_import_stubs
install_import_stubs()

from transport.config import (  # noqa: E402 (after stub install)
    _ACP_BACKEND_VALUES,
    _ALWAYS_ENABLED_BACKEND,
    ConfigError,
    parse_agent_backends,
)

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "scripts" / "lib" / "agent_backends.sh"
TOOLCHAINS = REPO / "crews" / "spec-ops" / "toolchains"

# Shared inputs: case, whitespace, empty entries, duplicates, kiro, order.
VECTORS = [
    "",
    "kiro",
    "claude",
    "codex",
    "claude,codex",
    "codex,claude",
    " Claude,,claude , CODEX",
    " Kiro, CODEX,,claude,codex",
    ",,,",
    "KIRO,kiro",
]


def _shell(func: str, *args: str) -> subprocess.CompletedProcess:
    script = f'source "{LIB}"; {func} "$@"'
    return subprocess.run(
        ["bash", "-c", script, "bash", *args],
        capture_output=True, text=True, timeout=30,
    )


class TestParserParity(unittest.TestCase):
    def test_normalised_lists_match(self):
        for raw in VECTORS:
            with self.subTest(raw=raw):
                shell = _shell("agent_backends_normalise", raw)
                self.assertEqual(shell.returncode, 0, shell.stderr)
                self.assertEqual(shell.stdout, ",".join(parse_agent_backends(raw)))

    def test_both_reject_an_unknown_name(self):
        with self.assertRaises(ConfigError):
            parse_agent_backends("claude,opencode")
        normalised = _shell("agent_backends_normalise", "claude,opencode").stdout
        self.assertNotEqual(
            _shell("agent_backends_validate", normalised, str(TOOLCHAINS)).returncode, 0
        )

    def test_shell_rejects_a_path_like_name(self):
        normalised = _shell("agent_backends_normalise", "../toolchains/claude").stdout
        result = _shell("agent_backends_validate", normalised, str(TOOLCHAINS))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GA_AGENT_BACKENDS", result.stderr)


class TestBackendsMatchToolchains(unittest.TestCase):
    def test_transport_optional_backends_match_toolchain_scripts(self):
        scripts = {p.stem for p in TOOLCHAINS.glob("*.sh")}
        optional = set(_ACP_BACKEND_VALUES) - {_ALWAYS_ENABLED_BACKEND}
        self.assertEqual(scripts, optional)

    def test_shell_lists_the_same_toolchains(self):
        available = _shell("agent_backends_available", str(TOOLCHAINS)).stdout
        self.assertEqual(set(filter(None, available.split(","))),
                         {p.stem for p in TOOLCHAINS.glob("*.sh")})


class TestShellDefaultAndRetired(unittest.TestCase):
    def test_default_outside_set_rejected(self):
        result = _shell("agent_backends_check_default", "codex", "claude")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GA_CREW_ACP_BACKEND", result.stderr)
        self.assertIn("GA_AGENT_BACKENDS", result.stderr)

    def test_kiro_default_always_accepted(self):
        self.assertEqual(_shell("agent_backends_check_default", "kiro", "").returncode, 0)

    def test_retired_flag_rejected_even_when_false(self):
        result = subprocess.run(
            ["bash", "-c", f'source "{LIB}"; agent_backends_reject_retired'],
            capture_output=True, text=True, timeout=30,
            env={"PATH": "/usr/bin:/bin", "GA_INCLUDE_CLAUDE_AGENT": "false"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GA_AGENT_BACKENDS", result.stderr)


if __name__ == "__main__":
    unittest.main()
