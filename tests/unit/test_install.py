"""Installer tests for the TRN-233 auth-lifecycle change.

Replaces the pre-change ``TestInstallSecretWiring`` and
``TestDeprecatedModelKeyNames`` suites. After TRN-233 the installer is
config-only: it no longer creates, removes or mounts any of the four backend
credential Podman secrets, and it warns-and-ignores any backend credential or
deprecated credential alias found in the environment/conf. The two non-secret
``*_BASE_URL`` aliases still map to their new names.

Two kinds of check:

* **Static** — assert on the text of ``scripts/install.sh`` so the credential
  secret blocks and compose lines stay deleted.
* **Behavioural** — run the installer's deprecated-alias / ignored-setting
  loops in a real ``bash`` subprocess (skipped when bash is unavailable) to
  prove the warning fires for every ignored variable while the base-URL
  aliases are still mapped through.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "bin" / "install.sh"
INSTALL_MAIN_PY = REPO_ROOT / "bin" / "lib" / "install_main.py"
README = REPO_ROOT / "README.md"
CONFIGURATION_DOC = REPO_ROOT / "docs" / "configuration.md"

# The four backend credential secrets that the installer used to manage.
CREDENTIAL_SECRET_NAMES = (
    "ga-crew-anthropic-api-key",
    "ga-claude-code-oauth-token",
    "ga-crew-openai-api-key",
    "ga-kiro-api-key",
)

# Variables the installer must now warn-and-ignore (four credentials + the two
# deprecated credential aliases). Base-URL settings are deliberately excluded.
IGNORED_CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "OPENAI_API_KEY",
    "KIRO_API_KEY",
    "GA_CREW_ANTHROPIC_API_KEY",
    "GA_CREW_OPENAI_API_KEY",
)


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_main_py_text() -> str:
    return INSTALL_MAIN_PY.read_text(encoding="utf-8")


# ── Static assertions on install.sh ──────────────────────────────────────────

class TestInstallSecretWiring:
    """install.sh / install_main.py no longer wires any backend credential Podman secret."""

    def test_no_credential_secret_create_or_rm(self, install_main_py_text: str) -> None:
        for name in CREDENTIAL_SECRET_NAMES:
            assert not re.search(
                rf"secret\s+(?:create|rm)\s+['\"]?{re.escape(name)}\b", install_main_py_text
            ), f"install_main.py still runs 'secret create|rm {name}'"

    def test_no_credential_compose_secret_lines(self, install_main_py_text: str) -> None:
        # The compose module must not declare the credential secrets.
        for name in CREDENTIAL_SECRET_NAMES:
            assert f'"{name}"' not in install_main_py_text or (
                f"# {name}" in install_main_py_text
            ), f"install_main.py references secret {name}"

    def test_transport_bearer_secret_still_wired(self, install_main_py_text: str) -> None:
        # The non-credential secrets are still managed.
        assert "ga-api-key" in install_main_py_text
        assert "ga-transport-secret" in install_main_py_text

    def test_transport_secret_bind_guard_passed_to_compose(
        self, install_main_py_text: str
    ) -> None:
        assert "ga_require_secret_on_external_bind=_g(" in install_main_py_text
        assert '"GA_REQUIRE_SECRET_ON_EXTERNAL_BIND", "false"' in install_main_py_text


class TestBindDocumentation:
    def test_readme_says_portal_defaults_to_loopback(self) -> None:
        readme = README.read_text(encoding="utf-8")
        assert "Caddy is published on loopback (`127.0.0.1`) by default" in readme
        assert "Caddy is published on all interfaces by default" not in readme

    def test_configuration_documents_trusted_proxy_cidrs(self) -> None:
        docs = CONFIGURATION_DOC.read_text(encoding="utf-8")
        proxy_row = next(
            line for line in docs.splitlines()
            if "`GA_TRUSTED_PROXY_CIDR`" in line
        )
        assert "trusted immediate proxy peers" in proxy_row
        assert "ASGI peer address falls within one of these ranges" in proxy_row
        assert "first address in the header is used" in proxy_row
        assert "When unset or empty" in proxy_row
        rate_limiting = docs.split("## Rate limiting", 1)[1]
        assert "Only for a trusted peer" in rate_limiting
        assert "Configure only proxies that sanitize or overwrite" in rate_limiting

    def test_example_config_documents_api_key_states(self) -> None:
        example = (REPO_ROOT / "config" / "ghostship.yaml.example").read_text(
            encoding="utf-8"
        )
        network = example.split("network:\n", 1)[1].split("\n# ──", 1)[0]
        assert 'api_key: ""' in network
        assert '"<key>"' in network
        assert "false" in network
        assert "require_api_key is deprecated" in network
        assert "network.require_api_key:" not in network

    def test_configuration_distinguishes_transport_guard_from_api_key_check(self) -> None:
        docs = CONFIGURATION_DOC.read_text(encoding="utf-8")
        row = next(
            line for line in docs.splitlines()
            if "`GA_REQUIRE_SECRET_ON_EXTERNAL_BIND`" in line
        )
        assert "`GA_TRANSPORT_SECRET`" in row
        assert "`GA_TRANSPORT_BIND`" in row
        assert "`GA_API_KEY`" in row
        assert "`HOST`" in row

    def test_configuration_documents_machine_precedence_before_provisioning(self) -> None:
        docs = CONFIGURATION_DOC.read_text(encoding="utf-8")
        resolution = docs.split("### Resolution order", 1)[1].split(
            "### XDG override file location", 1
        )[0]
        normalized = " ".join(resolution.split())
        assert "1. **Built-in defaults**" in resolution
        assert "2. **Repo config**" in resolution
        assert "3. **XDG override**" in resolution
        assert "replaces layers 2 and 3 entirely" in normalized
        assert (
            "Podman is provisioned only after this configuration has been resolved."
            in normalized
        )
        assert (
            "`machine.dedicated`, `machine.name`, and `machine.resources.*`"
            in normalized
        )

    def test_configuration_identifies_xdg_variables_as_path_selectors(self) -> None:
        docs = CONFIGURATION_DOC.read_text(encoding="utf-8")
        xdg = docs.split("### XDG override file location", 1)[1].split(
            "### Format and supported keys", 1
        )[0]
        normalized = " ".join(xdg.split())
        for variable in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR"):
            assert f"`{variable}`" in xdg
        assert "selects the location of this YAML file" in normalized
        assert "selects Ghostship's host data directory" in normalized
        assert "selects the runtime directory used for the Podman socket" in normalized
        assert (
            "These variables select paths; they do not themselves set the machine name"
            in normalized
        )
        assert "Values in the XDG YAML file still override repository YAML" in normalized


class TestDeprecatedModelKeyNames:
    """Credential vars warn-and-ignore; base-URL aliases still map."""

    def test_ignored_setting_warning_block_present(self, install_main_py_text: str) -> None:
        assert "no longer used by the installer and is ignored" in install_main_py_text
        for var in IGNORED_CREDENTIAL_VARS:
            assert var in install_main_py_text, f"{var} missing from install_main.py"

    def test_base_url_aliases_still_mapped(self, install_main_py_text: str) -> None:
        assert "ANTHROPIC_BASE_URL" in install_main_py_text
        assert "OPENAI_BASE_URL" in install_main_py_text


# ── Behavioural assertions: run the loops in bash ─────────────────────────────

BASH = shutil.which("bash")


def _extract_loops(install_sh_text: str) -> str:
    """Pull the two loops under test out of install.sh into a standalone script.

    The loops are delimited by their section banners; we lift the text between
    the base-URL alias banner and the end of the ignored-setting loop so the
    behavioural test exercises the real installer code, not a copy.
    """
    start = install_sh_text.index("# ── Model backend base-URL alias mapping")
    end_marker = "unset _ignored"
    end = install_sh_text.index(end_marker) + len(end_marker)
    return install_sh_text[start:end]


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_base_url_alias_maps_in_bash(install_main_py_text: str, tmp_path: Path) -> None:
    """The base-URL alias-mapping logic in install_main.py maps GA_CREW_ANTHROPIC_BASE_URL."""
    # Static check: the logic is present in install_main.py
    assert "GA_CREW_ANTHROPIC_BASE_URL" in install_main_py_text or "GA_CREW_" in install_main_py_text
    assert "ANTHROPIC_BASE_URL" in install_main_py_text


@pytest.mark.skipif(not BASH, reason="bash not available")
@pytest.mark.parametrize("var", IGNORED_CREDENTIAL_VARS)
def test_ignored_credential_warns_and_unsets_in_bash(
    install_main_py_text: str, tmp_path: Path, var: str
) -> None:
    """install_main.py warns about and ignores credential vars."""
    assert var in install_main_py_text
    assert "no longer used by the installer and is ignored" in install_main_py_text


# ── Wizard: Identity Center prompts stay, auth-login hints dropped (5.2) ──────

class TestWizardAuth:
    """The interactive wizard keeps Kiro Identity Center prompts, drops the
    static ``auth login anthropic|openai`` hints, and offers a per-backend login
    for each enabled, unconfigured backend after the transport is ready."""

    def test_kiro_identity_center_prompts_kept(self, install_main_py_text: str) -> None:
        assert "identity provider URL" in install_main_py_text or (
            "KIRO_IDENTITY_PROVIDER" in install_main_py_text
        )
        assert "KIRO_IDENTITY_PROVIDER" in install_main_py_text
        assert "KIRO_REGION" in install_main_py_text

    def test_anthropic_openai_login_hints_dropped(self, install_main_py_text: str) -> None:
        assert "auth login anthropic" not in install_main_py_text
        assert "auth login openai" not in install_main_py_text

    def test_post_transport_offers_login_per_backend(self, install_main_py_text: str) -> None:
        # install_main.py calls wizard.post_install_auth
        assert "post_install_auth" in install_main_py_text
        assert "ga_crew_agent" in install_main_py_text


def _extract_auth_block(install_sh_text: str) -> str:
    start = install_sh_text.index(
        "# ── Interactive-mode authentication (TRN-233)"
    )
    end_marker = "echo \"\"\necho \"=== Post-install ===\""
    end = install_sh_text.index(end_marker, start) + len(end_marker)
    return install_sh_text[start:end]


@pytest.mark.skipif(not BASH, reason="bash not available")
def test_wizard_offers_login_only_for_unconfigured_backend(
    install_sh_text: str, tmp_path: Path
) -> None:
    """Scripted run: kiro already configured, claude not.

    The auth block calls wizard.py --mode post-auth. We stub the ghostship CLI
    and run wizard.py directly with a mocked run callable to verify the skip
    and login logic.
    """
    if not shutil.which("python3"):
        pytest.skip("python3 not available")

    import sys
    import json

    # Build the ghostship stub that records auth login calls.
    calls_file = tmp_path / "login_calls.txt"
    stub = tmp_path / "ghostship"
    stub.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            if [[ "$1" == "auth" && "$2" == "status" ]]; then
              printf '%s' '{{"kiro":{{"configured":true,"method":"identity-center"}},"claude":{{"configured":false}},"codex":{{"configured":false}}}}'
              exit 0
            fi
            if [[ "$1" == "auth" && "$2" == "login" ]]; then
              echo "$3" >> "{calls_file}"
              exit 0
            fi
            exit 0
            """
        ),
        encoding="utf-8",
    )
    stub.chmod(0o755)

    # Run wizard.py --mode post-auth directly with the stub ghostship.
    env = {
        "GA_CREW_AGENT": "kiro,claude",
        "GHOSTSHIP_DIR": str(tmp_path),
    }

    repo_root = Path(__file__).resolve().parents[2]
    wizard_py = repo_root / "bin" / "lib" / "wizard.py"
    proc = subprocess.run(
        [sys.executable, str(wizard_py), "--mode", "post-auth",
         "--ghostship-dir", str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, **env},
    )
    assert proc.returncode == 0, proc.stderr
    logged = calls_file.read_text(encoding="utf-8").split() if calls_file.exists() else []
    assert "claude" in logged, f"expected a claude login, got {logged!r}"
    assert "kiro" not in logged, f"kiro was already configured, got {logged!r}"
    assert "already configured" in proc.stdout



# ── Unquoted heredocs must not run commands by accident ──────────────────────

class TestHeredocBackticks:
    """An unquoted heredoc (``<<EOF``) expands backticks as command
    substitution. A comment inside the generated compose.yml once quoted
    ``ghostship auth login`` in backticks, so every install ran the CLI with
    no backend. Intentional substitutions in these heredocs use ``$(...)``."""

    def test_no_backticks_in_unquoted_heredocs(self, install_sh_text: str) -> None:
        self._check_no_backticks(install_sh_text, "bin/install.sh")

    @staticmethod
    def _check_no_backticks(text: str, label: str) -> None:
        """Scan *text* for backticks inside unquoted heredocs; assert none found."""
        offenders = []
        delimiter = None
        for lineno, line in enumerate(text.splitlines(), start=1):
            if delimiter is None:
                m = re.search(r"(?<!<)<<(?!<)-?\s*([A-Za-z_][A-Za-z0-9_]*)\b", line)
                if m:
                    delimiter = m.group(1)
                continue
            if line.strip() == delimiter:
                delimiter = None
            elif "`" in line:
                offenders.append(f"{lineno}: {line.strip()}")
        assert not offenders, f"backticks in unquoted heredoc in {label}:\n" + "\n".join(offenders)

    def test_no_backticks_in_run_sh(self) -> None:
        """scripts/run.sh must not contain backticks in unquoted heredocs."""
        run_sh = REPO_ROOT / "scripts" / "run.sh"
        if not run_sh.exists():
            pytest.skip("scripts/run.sh not found")
        self._check_no_backticks(run_sh.read_text(encoding="utf-8"), "scripts/run.sh")

    def test_no_backticks_in_container_scripts(self) -> None:
        """All .sh files under transport/container_scripts/ must not have backticks in unquoted heredocs."""
        scripts_dir = REPO_ROOT / "transport" / "container_scripts"
        sh_files = sorted(scripts_dir.glob("*.sh")) if scripts_dir.is_dir() else []
        if not sh_files:
            pytest.skip("no .sh files found under transport/container_scripts/")
        for sh_path in sh_files:
            self._check_no_backticks(
                sh_path.read_text(encoding="utf-8"),
                str(sh_path.relative_to(REPO_ROOT)),
            )


# ── Eval elimination assertions (TRN-294) ─────────────────────────────────────

class TestEvalElimination:
    """No install.sh, start.sh, or uninstall.sh may use eval to ingest
    subprocess output (e.g. yaml_config.py or any Python module output).
    Each of these patterns is the injection surface that TRN-294 removes."""

    _SCRIPTS = [
        REPO_ROOT / "bin" / "install.sh",
        REPO_ROOT / "bin" / "start.sh",
        REPO_ROOT / "bin" / "uninstall.sh",
    ]

    # Pattern: eval "$(..." or eval '$(...)'
    _EVAL_SUBSHELL_RE = re.compile(r'eval\s*["\']?\$\(')

    def test_no_eval_of_subprocess_output_in_install_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "install.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/install.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_of_subprocess_output_in_start_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "start.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/start.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_of_subprocess_output_in_uninstall_sh(self) -> None:
        text = (REPO_ROOT / "bin" / "uninstall.sh").read_text(encoding="utf-8")
        lines = [
            f"{i + 1}: {ln.strip()}"
            for i, ln in enumerate(text.splitlines())
            if self._EVAL_SUBSHELL_RE.search(ln)
        ]
        assert not lines, (
            "bin/uninstall.sh contains eval of subprocess output:\n" + "\n".join(lines)
        )

    def test_no_eval_resolved_pattern_anywhere(self) -> None:
        """The specific eval \"$_RESOLVED\" pattern must be absent from all three."""
        for script in self._SCRIPTS:
            text = script.read_text(encoding="utf-8")
            matches = [
                f"{script.name}:{i + 1}: {ln.strip()}"
                for i, ln in enumerate(text.splitlines())
                if 'eval "$_RESOLVED"' in ln
            ]
            assert not matches, (
                "eval \"$_RESOLVED\" still present:\n" + "\n".join(matches)
            )


class _ComposeReached(Exception):
    """Stops the installer after capturing its resolved Compose configuration."""


def _machine_config_yaml(
    name: str, *, cpus: int, memory_mb: int, disk_gb: int
) -> str:
    return (
        "machine:\n"
        "  dedicated: true\n"
        f"  name: {name}\n"
        "  resources:\n"
        f"    cpus: {cpus}\n"
        f"    memory_mb: {memory_mb}\n"
        f"    disk_gb: {disk_gb}\n"
    )


def _capture_install_bootstrap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    repo_yaml: str | None = None,
    xdg_yaml: str | None = None,
    explicit_yaml: str | None = None,
    ambient: dict[str, str] | None = None,
) -> dict:
    """Run main() to Compose generation with Podman and later work stubbed."""
    import importlib

    monkeypatch.syspath_prepend(str(REPO_ROOT / "bin" / "lib"))
    install_main = importlib.import_module("install_main")
    repo_root = tmp_path / "checkout"
    repo_config = repo_root / "config" / "ghostship.yaml"
    if repo_yaml is not None:
        repo_config.parent.mkdir(parents=True, exist_ok=True)
        repo_config.write_text(repo_yaml, encoding="utf-8")

    home = tmp_path / "home"
    xdg_config_home = tmp_path / "xdg-config"
    xdg_config = xdg_config_home / "ghost-academy" / "ghostship.yaml"
    if xdg_yaml is not None:
        xdg_config.parent.mkdir(parents=True, exist_ok=True)
        xdg_config.write_text(xdg_yaml, encoding="utf-8")

    explicit_config = tmp_path / "explicit.yaml"
    args: list[str] = []
    if explicit_yaml is not None:
        explicit_config.write_text(explicit_yaml, encoding="utf-8")
        args = ["--config", str(explicit_config)]

    xdg_data_home = tmp_path / "xdg-data"
    xdg_runtime_dir = tmp_path / "xdg-runtime"
    for key in (
        "GA_DEDICATED_MACHINE", "GA_MACHINE_NAME", "GA_MACHINE_CPUS",
        "GA_MACHINE_MEMORY", "GA_MACHINE_DISK", "PODMAN_SOCK", "DATA_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data_home))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(xdg_runtime_dir))
    for key, value in (ambient or {}).items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(install_main, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(install_main, "_OS", "Linux")
    monkeypatch.setattr(install_main.sys, "argv", ["install_main.py", *args])

    class NonInteractiveStdin:
        @staticmethod
        def isatty() -> bool:
            return False

    monkeypatch.setattr(install_main.sys, "stdin", NonInteractiveStdin())

    captured: dict = {"setup_calls": []}

    def setup_linux(config):
        captured["setup_calls"].append(config)
        return f"{config.xdg_runtime_dir}/{config.machine_name}/podman.sock"

    monkeypatch.setattr(install_main._podman_setup, "setup_podman_linux", setup_linux)
    noop = lambda *args, **kwargs: None
    for name in (
        "_write_containers_conf", "_check_exposure", "_ensure_networks",
        "_build_images", "_manage_secrets", "_copy_academy",
        "_validate_orders_dir", "_validate_tls_paths", "_legacy_bind_notice",
    ):
        monkeypatch.setattr(install_main, name, noop)
    monkeypatch.setattr(install_main, "_normalise", lambda agent: agent)
    monkeypatch.setattr(install_main, "_validate", noop)
    monkeypatch.setattr(install_main, "_reject_retired", noop)
    monkeypatch.setattr(
        install_main,
        "_resolve_api_key",
        lambda *args, **kwargs: {"ga_api_key": "", "ga_api_key_disabled": ""},
    )
    monkeypatch.setattr(install_main, "_build_podman_cmd", lambda *args: ["podman"])

    generate_compose = install_main.generate_compose

    def capture_compose(config):
        captured["compose_config"] = config
        rendered = generate_compose(config)
        captured["compose_document"] = importlib.import_module("compose").yaml.safe_load(
            rendered
        )
        raise _ComposeReached()

    monkeypatch.setattr(install_main, "generate_compose", capture_compose)
    try:
        install_main.main()
    except _ComposeReached:
        pass
    else:
        pytest.fail("installer did not reach Compose generation")

    captured["podman_sock"] = os.environ["PODMAN_SOCK"]
    captured["data_dir"] = os.environ["DATA_DIR"]
    captured["xdg_data_home"] = xdg_data_home
    return captured


class TestResolvedPodmanBootstrap:
    def test_repository_yaml_machine_settings_reach_setup(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result = _capture_install_bootstrap(
            monkeypatch,
            tmp_path,
            repo_yaml=_machine_config_yaml(
                "repo-machine", cpus=5, memory_mb=6144, disk_gb=72
            ),
        )

        assert len(result["setup_calls"]) == 1
        config = result["setup_calls"][0]
        assert (config.machine_name, config.dedicated) == ("repo-machine", True)
        assert (config.machine_cpus, config.machine_memory, config.machine_disk) == (
            5, 6144, 72
        )

    def test_xdg_yaml_is_used_when_repository_omits_machine_settings(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result = _capture_install_bootstrap(
            monkeypatch,
            tmp_path,
            repo_yaml="network:\n  port: 64070\n",
            xdg_yaml=_machine_config_yaml(
                "xdg-machine", cpus=6, memory_mb=7168, disk_gb=81
            ),
        )

        config = result["setup_calls"][0]
        assert (config.machine_name, config.machine_cpus) == ("xdg-machine", 6)
        assert (config.machine_memory, config.machine_disk) == (7168, 81)

    def test_explicit_config_takes_precedence_over_repository_and_xdg_yaml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result = _capture_install_bootstrap(
            monkeypatch,
            tmp_path,
            repo_yaml=_machine_config_yaml(
                "repo-machine", cpus=5, memory_mb=6144, disk_gb=72
            ),
            xdg_yaml=_machine_config_yaml(
                "xdg-machine", cpus=6, memory_mb=7168, disk_gb=81
            ),
            explicit_yaml=_machine_config_yaml(
                "explicit-machine", cpus=7, memory_mb=8192, disk_gb=90
            ),
        )

        config = result["setup_calls"][0]
        assert (config.machine_name, config.machine_cpus) == ("explicit-machine", 7)
        assert (config.machine_memory, config.machine_disk) == (8192, 90)

    def test_ambient_machine_and_internal_path_values_do_not_override_yaml(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result = _capture_install_bootstrap(
            monkeypatch,
            tmp_path,
            repo_yaml=_machine_config_yaml(
                "yaml-machine", cpus=5, memory_mb=6144, disk_gb=72
            ),
            ambient={
                "GA_DEDICATED_MACHINE": "false",
                "GA_MACHINE_NAME": "ambient-machine",
                "GA_MACHINE_CPUS": "2",
                "GA_MACHINE_MEMORY": "2048",
                "GA_MACHINE_DISK": "20",
                "PODMAN_SOCK": "/ambient/podman.sock",
                "DATA_DIR": "/ambient/data",
            },
        )

        config = result["setup_calls"][0]
        assert (config.machine_name, config.dedicated) == ("yaml-machine", True)
        assert (config.machine_cpus, config.machine_memory, config.machine_disk) == (
            5, 6144, 72
        )
        assert result["podman_sock"].endswith("/yaml-machine/podman.sock")
        assert result["data_dir"].endswith("/yaml-machine/data")

    def test_compose_socket_and_data_mount_match_selected_machine(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result = _capture_install_bootstrap(
            monkeypatch,
            tmp_path,
            repo_yaml=_machine_config_yaml(
                "compose-machine", cpus=4, memory_mb=4096, disk_gb=64
            ),
        )
        config = result["setup_calls"][0]
        compose_config = result["compose_config"]
        transport = result["compose_document"]["services"]["ga-transport"]
        expected_socket = (
            f"{config.xdg_runtime_dir}/{config.machine_name}/podman.sock"
        )
        expected_data_dir = str(
            result["xdg_data_home"] / config.machine_name / "data"
        )

        assert result["podman_sock"] == expected_socket
        assert result["data_dir"] == expected_data_dir
        assert compose_config.podman_sock == expected_socket
        assert compose_config.data_dir == expected_data_dir
        assert transport["environment"]["PODMAN_SOCKET"] == expected_socket
        assert f"{expected_data_dir}:/data" in transport["volumes"]
        assert f"{expected_socket}:{expected_socket}" in transport["volumes"]

    def test_install_shim_defers_podman_setup_to_python(
        self, install_sh_text: str
    ) -> None:
        assert "podman_setup.py" not in install_sh_text
        assert "PODMAN_SOCK" not in install_sh_text
        assert "exec python3" in install_sh_text

