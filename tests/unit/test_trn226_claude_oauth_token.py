"""TRN-226: headless Claude auth via CLAUDE_CODE_OAUTH_TOKEN.

The operator runs ``claude setup-token`` on their own machine and sets the
printed token as CLAUDE_CODE_OAUTH_TOKEN in ghostship.conf. install.sh delivers
it as the ga-claude-code-oauth-token Podman secret; the transport injects it
into Claude-backend crews.

Covers:
- install.sh: shell env never leaks in, secret + compose wiring is conditional.
- Credential resolution: server and lifecycle read every crew credential from
  the same Podman secret, so their precedence checks agree.
- Precedence: API key > token > ga-claude-auth, one credential per crew.
- Launch gate: the token alone satisfies Claude auth.
- Inert-setting warning names the token, never its value.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from transport.config import Config, inert_backend_settings

# ── Install stubs FIRST — before ANY transport import ─────────────────────────
from tests.unit._stubs import install_import_stubs
install_import_stubs()

import transport.lifecycle as _lifecycle  # noqa: E402 (after stub install)
import transport.server as _server       # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_INSTALL_SH = (_REPO / "scripts" / "install.sh").read_text()
_TOKEN = "sk-ant-oat01-THIS-MUST-NOT-BE-LOGGED"
_ALL_BACKENDS = Config(ga_crew_agent="kiro,claude,codex")


def _defaults_block() -> str:
    """install.sh's built-in defaults block (runs before any config sourcing)."""
    start = _INSTALL_SH.index("# ── Built-in defaults")
    end = _INSTALL_SH.index("# ── Config file: extract --config")
    return _INSTALL_SH[start:end]


def _run_bash(script: str, env: dict[str, str]) -> str:
    return subprocess.run(
        ["bash", "-c", script], env={"PATH": os.environ["PATH"], **env},
        capture_output=True, text=True, check=True,
    ).stdout


# ── install.sh ────────────────────────────────────────────────────────────────


class TestInstallDefaultsIgnoreShellEnv(unittest.TestCase):
    """Precedence is default → config → flag; the invoking shell never counts."""

    def test_token_exported_in_shell_is_reset(self) -> None:
        out = _run_bash(_defaults_block() + 'printf "%s" "$CLAUDE_CODE_OAUTH_TOKEN"',
                        {"CLAUDE_CODE_OAUTH_TOKEN": _TOKEN})
        self.assertEqual(out, "")

    def test_every_setting_install_reads_has_a_literal_default(self) -> None:
        """Any setting read without a default would let the shell leak in."""
        assigned = set(re.findall(r"^\s*([A-Z][A-Z0-9_]+)=", _defaults_block(), re.M))
        prefix = r"(?:GA|KC|KIRO|CLAUDE|ANTHROPIC|OPENAI)_[A-Z0-9_]+|HOST|PORT"
        used = set(re.findall(r"\$\{?(" + prefix + r")\b", _INSTALL_SH))
        self.assertEqual(sorted(used - assigned), [])

    def test_shell_values_do_not_override_defaults(self) -> None:
        leak = {"HOST": "203.0.113.9", "ANTHROPIC_BASE_URL": "http://evil",
                "GA_RATE_LIMIT_ENABLED": "false", "GA_DASHBOARD_DEFAULT": "true"}
        out = _run_bash(
            _defaults_block()
            + 'printf "%s|%s|%s|%s" "$HOST" "$ANTHROPIC_BASE_URL" '
              '"$GA_RATE_LIMIT_ENABLED" "$GA_DASHBOARD_DEFAULT"',
            leak,
        )
        self.assertEqual(out, "0.0.0.0||true|false")


def _alias_block() -> str:
    """install.sh's deprecated GA_CREW_* → standard-name mapping."""
    start = _INSTALL_SH.index("# ── Model backend setting names (TRN-226)")
    end = _INSTALL_SH.index("# ── Agent backend consolidation (TRN-213)")
    return _INSTALL_SH[start:end]


class TestDeprecatedModelKeyNames(unittest.TestCase):
    """GA_CREW_ANTHROPIC_* / GA_CREW_OPENAI_* still work, with a warning."""

    def _run(self, conf: str) -> subprocess.CompletedProcess:
        script = (_defaults_block() + conf + "\n" + _alias_block()
                  + 'printf "%s|%s|%s|%s" "$ANTHROPIC_API_KEY" "$ANTHROPIC_BASE_URL" '
                    '"$OPENAI_API_KEY" "$OPENAI_BASE_URL"')
        return subprocess.run(["bash", "-c", script], env={"PATH": os.environ["PATH"]},
                              capture_output=True, text=True, check=True)

    def test_old_names_map_to_new(self) -> None:
        r = self._run('GA_CREW_ANTHROPIC_API_KEY="ak"; GA_CREW_ANTHROPIC_BASE_URL="au"; '
                      'GA_CREW_OPENAI_API_KEY="ok"; GA_CREW_OPENAI_BASE_URL="ou"')
        self.assertEqual(r.stdout, "ak|au|ok|ou")
        for old in ("GA_CREW_ANTHROPIC_API_KEY", "GA_CREW_ANTHROPIC_BASE_URL",
                    "GA_CREW_OPENAI_API_KEY", "GA_CREW_OPENAI_BASE_URL"):
            self.assertIn(f"{old} is deprecated", r.stderr)

    def test_new_name_wins_when_both_set(self) -> None:
        r = self._run('ANTHROPIC_API_KEY="new"; GA_CREW_ANTHROPIC_API_KEY="old"')
        self.assertEqual(r.stdout.split("|")[0], "new")
        self.assertIn("ignoring GA_CREW_ANTHROPIC_API_KEY", r.stderr)

    def test_warning_never_prints_the_value(self) -> None:
        r = self._run('GA_CREW_ANTHROPIC_API_KEY="sk-ant-SECRET-VALUE"')
        self.assertNotIn("sk-ant-SECRET-VALUE", r.stderr)

    def test_new_names_alone_are_silent(self) -> None:
        r = self._run('ANTHROPIC_API_KEY="ak"; OPENAI_API_KEY="ok"')
        self.assertEqual(r.stdout, "ak||ok|")
        self.assertEqual(r.stderr, "")

    def test_old_names_exported_in_shell_are_ignored(self) -> None:
        script = _defaults_block() + _alias_block() + 'printf "%s" "$ANTHROPIC_API_KEY"'
        out = _run_bash(script, {"GA_CREW_ANTHROPIC_API_KEY": "leak", "ANTHROPIC_API_KEY": "leak"})
        self.assertEqual(out, "")


class TestInstallSecretWiring(unittest.TestCase):
    """CLAUDE_CODE_OAUTH_TOKEN reaches the transport only as a Podman secret."""

    _COMPOSE_LINES = [
        line for line in _INSTALL_SH.splitlines()
        if line.startswith("$(if") and "CLAUDE_CODE_OAUTH_TOKEN" in line
    ]

    def _compose_fragment(self, token: str) -> str:
        return _run_bash(
            "\n".join(f"echo \"{line}\"" for line in self._COMPOSE_LINES),
            {"CLAUDE_CODE_OAUTH_TOKEN": token} if token else {},
        )

    def test_secret_recreated_on_every_install(self) -> None:
        self.assertIn("secret rm ga-claude-code-oauth-token", _INSTALL_SH)
        self.assertRegex(
            _INSTALL_SH,
            r'printf \'%s\' "\$CLAUDE_CODE_OAUTH_TOKEN" \| \$\{_PODMAN_CMD\} '
            r"secret create ga-claude-code-oauth-token -",
        )

    def test_compose_lists_secret_when_token_set(self) -> None:
        self.assertEqual(len(self._COMPOSE_LINES), 2)  # service list + top-level block
        out = self._compose_fragment(_TOKEN)
        self.assertIn("      - ga-claude-code-oauth-token", out)
        self.assertIn("  ga-claude-code-oauth-token:\n    external: true", out)
        self.assertNotIn(_TOKEN, out)

    def test_no_dangling_reference_when_token_unset(self) -> None:
        self.assertNotIn("ga-claude-code-oauth-token", self._compose_fragment(""))

    def test_token_never_in_compose_environment(self) -> None:
        self.assertNotRegex(_INSTALL_SH, r"^\s+CLAUDE_CODE_OAUTH_TOKEN:", )


# ── Credential resolution ─────────────────────────────────────────────────────


class TestCredentialsResolvedFromSecrets(unittest.TestCase):
    """server and lifecycle must read the same secret for every credential.

    Before TRN-226 lifecycle used the cfg (env) values, which are "" in
    production, so its OAuth-injection guards ignored a configured API key.
    """

    CREDENTIALS = {
        "KIRO_API_KEY": "ga-kiro-api-key",
        "ANTHROPIC_API_KEY": "ga-crew-anthropic-api-key",
        "OPENAI_API_KEY": "ga-crew-openai-api-key",
        "CLAUDE_CODE_OAUTH_TOKEN": "ga-claude-code-oauth-token",
    }

    def test_both_modules_resolve_each_credential_from_its_secret(self) -> None:
        for module in (_server, _lifecycle):
            src = Path(module.__file__).read_text()
            for env_var, secret in self.CREDENTIALS.items():
                with self.subTest(module=module.__name__, env_var=env_var):
                    self.assertRegex(
                        src,
                        rf'get_secret\(\s*"{secret}",\s*env_var="{env_var}"\)',
                    )

    def test_get_secret_prefers_the_mounted_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            secret = Path(d) / "ga-claude-code-oauth-token"
            secret.write_text(_TOKEN + "\n")
            with patch.dict(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN": "from-env"}):
                value = _server._security.get_secret(
                    "ga-claude-code-oauth-token", secret_file=str(secret),
                    env_var="CLAUDE_CODE_OAUTH_TOKEN")
        self.assertEqual(value, _TOKEN)
        self.assertNotIn(_TOKEN, _server._security.redact(f"token={_TOKEN}"))


# ── Crew env injection and precedence ─────────────────────────────────────────


def _launch_env(*, backend: str, api_key: str, token: str, oauth: bool = False) -> dict:
    """Run server.launch() far enough to capture the container_create env."""
    captured: dict = {}
    podman = Mock()
    podman.container_create.side_effect = lambda *a, **kw: captured.update(kw.get("env", {}))
    with (
        patch.object(_server, "GA_CREW_ACP_BACKEND", backend),
        patch.object(_server, "cfg", _ALL_BACKENDS),
        patch.object(_server, "_ANTHROPIC_API_KEY", api_key),
        patch.object(_server, "_ANTHROPIC_BASE_URL", ""),
        patch.object(_server, "_CLAUDE_CODE_OAUTH_TOKEN", token),
        patch.object(_server, "_claude_auth_exists", return_value=oauth),
        patch.object(_server, "KIRO_API_KEY", "kiro-key"),
        patch.object(_server, "_read_auth_file", return_value=""),
        patch.object(_server, "_get_podman", return_value=podman),
        patch.object(_lifecycle, "_get_podman", return_value=podman),
        patch.object(_server, "_load_registry", return_value={"crews": {}}),
        patch.object(_lifecycle, "_load_registry", return_value={"crews": {}}),
        patch.object(_server, "_save_registry"),
        patch.object(_lifecycle, "_save_registry"),
        patch.object(_server, "_wait_gateway", return_value=True),
        patch.object(_server, "_finish_crew_setup",
                     Mock(return_value={"crew_id": "c", "status": "ready"})),
        patch.object(_server, "_write_crew_secret"),
    ):
        _server.launch("test-crew")
    return captured


class TestTokenInjection(unittest.TestCase):
    def test_token_injected_when_no_api_key(self) -> None:
        env = _launch_env(backend="claude", api_key="", token=_TOKEN)
        self.assertEqual(env.get("CLAUDE_CODE_OAUTH_TOKEN"), _TOKEN)
        self.assertNotIn("ANTHROPIC_API_KEY", env)

    def test_api_key_outranks_token(self) -> None:
        env = _launch_env(backend="claude", api_key="sk-ant-api", token=_TOKEN)
        self.assertEqual(env.get("ANTHROPIC_API_KEY"), "sk-ant-api")
        self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)

    def test_token_not_injected_into_non_claude_crews(self) -> None:
        for backend in ("kiro", "codex"):
            with self.subTest(backend=backend):
                env = _launch_env(backend=backend, api_key="", token=_TOKEN)
                self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", env)


class TestOAuthInjectionSkipped(unittest.TestCase):
    """_finish_crew_setup copies ga-claude-auth only when no other credential."""

    def _finish_setup(self, *, api_key: str, token: str) -> Mock:
        podman = Mock()
        podman.container_exec.return_value = "ready"
        podman.container_inspect.return_value = {
            "Config": {"Labels": {"org.ghostship.version": "v"}},
            "State": {"StartedAt": "2026-01-01T00:00:00Z"},
        }
        stubs = ["_patch_crew_config", "_copy_agents", "_copy_skills", "_copy_steering",
                 "_seed_openspec_store", "_patch_models", "_save_registry",
                 "_cleanup_crew", "_inject_auth"]
        with (
            patch.object(_lifecycle, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(_lifecycle, "ANTHROPIC_API_KEY", api_key),
            patch.object(_lifecycle, "CLAUDE_CODE_OAUTH_TOKEN", token),
            patch.object(_lifecycle, "_claude_auth_exists", return_value=True),
            patch.object(_lifecycle, "_inject_claude_auth") as inject,
            patch.object(_lifecycle, "_wait_gateway", return_value=True),
            patch.object(_lifecycle, "_mint_cookie", return_value="cookie"),
            patch.object(_lifecycle, "_inject_policy", return_value="v1"),
            patch.object(_lifecycle, "_load_registry", return_value={"crews": {"test-crew": {}}}),
        ):
            for name in stubs:
                patch.object(_lifecycle, name).start()
            try:
                _lifecycle._finish_crew_setup(
                    podman, "test-crew", "gs-test-crew", "gs-vol", "gs-home", None,
                    admiral_secret="a" * 64,
                )
            finally:
                patch.stopall()
        return inject

    def test_skipped_when_token_set(self) -> None:
        self._finish_setup(api_key="", token=_TOKEN).assert_not_called()

    def test_skipped_when_api_key_set(self) -> None:
        self._finish_setup(api_key="sk-ant-api", token="").assert_not_called()

    def test_used_as_fallback(self) -> None:
        self._finish_setup(api_key="", token="").assert_called_once()


# ── Launch gate ───────────────────────────────────────────────────────────────


class TestLaunchGate(unittest.TestCase):
    def _launch(self, *, token: str) -> tuple[dict, Mock]:
        with (
            patch.object(_server, "GA_CREW_ACP_BACKEND", "claude"),
            patch.object(_server, "cfg", _ALL_BACKENDS),
            patch.object(_server, "_ANTHROPIC_API_KEY", ""),
            patch.object(_server, "_CLAUDE_CODE_OAUTH_TOKEN", token),
            patch.object(_server, "_claude_auth_exists", return_value=False),
            patch.object(_server, "_initiate_claude_login",
                         return_value={"login_url": "https://example.test", "code": None}) as login,
            patch.object(_server, "_get_podman", return_value=Mock()),
            patch.object(_server, "_load_registry", return_value={"crews": {}}),
            patch.object(_lifecycle, "_load_registry", return_value={"crews": {}}),
            patch.object(_server, "_save_registry"),
            patch.object(_lifecycle, "_save_registry"),
            patch.object(_server, "_wait_gateway", return_value=True),
            patch.object(_server, "_finish_crew_setup",
                         Mock(return_value={"crew_id": "c", "status": "ready"})),
            patch.object(_server, "_write_crew_secret"),
        ):
            return _server.launch("test-crew"), login

    def test_token_alone_satisfies_auth(self) -> None:
        result, login = self._launch(token=_TOKEN)
        self.assertNotEqual(result.get("error"), "not_authenticated", result)
        login.assert_not_called()

    def test_no_credential_still_prompts_for_login(self) -> None:
        result, login = self._launch(token="")
        self.assertEqual(result.get("error"), "not_authenticated")
        self.assertEqual(result.get("login_url"), "https://example.test")
        login.assert_called_once()


# ── Inert-setting warning ─────────────────────────────────────────────────────


class TestInertToken(unittest.TestCase):
    def test_token_inert_when_claude_disabled(self) -> None:
        cfg = Config(ga_crew_agent="kiro", claude_code_oauth_token=_TOKEN)
        self.assertEqual(inert_backend_settings(cfg, frozenset()), ["CLAUDE_CODE_OAUTH_TOKEN"])

    def test_not_inert_when_claude_enabled(self) -> None:
        cfg = Config(ga_crew_agent="kiro,claude", claude_code_oauth_token=_TOKEN)
        self.assertEqual(inert_backend_settings(cfg, frozenset()), [])

    def test_warning_uses_secret_value_and_never_logs_it(self) -> None:
        with (
            patch.object(_server, "cfg", Config(ga_crew_agent="kiro")),
            patch.object(_server, "_CLAUDE_CODE_OAUTH_TOKEN", _TOKEN),
            patch.object(_server, "_claude_auth_exists", return_value=False),
            patch.object(_server, "_codex_auth_exists", return_value=False),
            self.assertLogs(_server.logger, level=logging.WARNING) as logs,
        ):
            _server._warn_inert_backend_settings()
        output = "\n".join(logs.output)
        self.assertEqual(output.count("CLAUDE_CODE_OAUTH_TOKEN"), 1)
        self.assertNotIn(_TOKEN, output)


if __name__ == "__main__":
    unittest.main()
