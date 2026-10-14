"""LoginFlow class hierarchy for the three ACP backend device-code auth flows.

Each backend (kiro, claude, codex) has a concrete ``LoginFlow`` subclass with
backend-specific configuration and hooks. The shared state machine and lifecycle
(initiate, abort, is_expired, start_container) live in the ``LoginFlow`` ABC.

After TRN-240 task 5.3 migrates lifecycle.py, the existing module-level
functions (_initiate_login, _abort_pending_login, etc.) become one-line wrappers
delegating to the singletons defined at the bottom of this module. Until then,
the classes co-exist alongside the existing functions.

Design note: the three module-level singletons (KIRO_FLOW, CLAUDE_FLOW,
CODEX_FLOW) hold state for in-progress flows. Each singleton is not reentrant
— concurrent callers are serialised by the per-flow ``_lock``.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from abc import ABC, abstractmethod
from typing import ClassVar

try:
    from config import Config  # container: flat /app/
except ImportError:
    from transport.config import Config  # local dev

try:
    from constants import SCRIPTS_DIR  # container: flat /app/
except ModuleNotFoundError:
    from transport.constants import SCRIPTS_DIR  # local dev

logger = logging.getLogger(__name__)

cfg = Config.from_env()

# ── Shared constants ──────────────────────────────────────────────────────────

_KIRO_LOGIN_TTL_SECS = 900.0
_CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS = 900.0
_CLAUDE_LOGIN_CODE_DEADLINE_SECS = 120.0
_CODEX_LOGIN_TTL_SECS = 900.0

_GA_LOGIN_CONTAINER_PREFIX = "ga-login-"
_GA_CLAUDE_LOGIN_CONTAINER_PREFIX = "ga-claude-login-"
_GA_CODEX_LOGIN_CONTAINER_PREFIX = "ga-codex-login-"

try:
    from constants import GA_STARBOARD_NETWORK  # noqa: F401
except ModuleNotFoundError:
    from transport.constants import GA_STARBOARD_NETWORK  # noqa: F401


# ── Abstract base class ───────────────────────────────────────────────────────


class LoginFlow(ABC):
    """Abstract base class for ACP backend device-code authentication flows.

    Subclasses implement backend-specific behaviour by overriding the abstract
    hook methods. The shared ``initiate``, ``abort``, and ``is_expired`` methods
    provide the common state-machine skeleton.

    Instance state is guarded by ``self._lock`` (a plain threading.Lock).
    The flow is stateful: ``self._pending`` holds the in-progress flow dict
    (or ``None`` when idle), mirroring the module-level ``_login_pending``
    dicts in lifecycle.py.
    """

    # ── Class-level metadata (set by subclasses) ──────────────────────────────
    backend: ClassVar[str]          # e.g. "kiro", "claude", "codex"
    container_prefix: ClassVar[str]  # prefix for ephemeral login containers
    image_key: ClassVar[str]         # "kc_base_image" or "kc_image"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict | None = None

    # ── Abstract hooks (implemented by subclasses) ────────────────────────────

    @abstractmethod
    def _binary_name(self) -> str:
        """Return the CLI binary name (e.g. "kiro-cli", "claude", "codex-acp")."""

    @abstractmethod
    def _login_cmd(self) -> list[str]:
        """Return the full command to run inside the container for the login flow."""

    @abstractmethod
    def _prompt_patterns(self) -> list[tuple]:
        """Return a list of (compiled_regex, answer_bytes) prompt patterns."""

    @abstractmethod
    def _url_patterns(self) -> list:
        """Return a list of compiled regexes that match the device-flow URL."""

    @abstractmethod
    def _code_pattern(self):
        """Return a compiled regex that extracts the device-flow code from text."""

    @abstractmethod
    def _ttl_secs(self) -> float:
        """Return the TTL in seconds for this flow."""

    @abstractmethod
    def auth_exists(self) -> bool:
        """True if stored credentials for this backend already exist."""

    @abstractmethod
    def write_auth(self, podman, container: str, auth_b64: str) -> None:
        """Persist the auth credential from the completed login flow."""

    @abstractmethod
    def inject_auth(self, podman, container: str) -> None:
        """Inject the stored credential into a crew container at launch time."""

    @abstractmethod
    def poll(self, podman) -> bytes | str | None:
        """Poll the in-progress login container for a completed credential.

        Returns the credential (bytes or base64 str) on success, None if not
        yet complete.
        """

    @abstractmethod
    def _container_create_payload(self, name: str) -> dict:
        """Return the Podman container-create JSON payload for the login container."""

    # ── Shared implementation ─────────────────────────────────────────────────

    @property
    def state(self) -> dict | None:
        """Current pending-flow state dict, or None when idle."""
        return self._pending

    def is_expired(self) -> bool:
        """True when the in-progress flow has exceeded its TTL."""
        with self._lock:
            pending = self._pending
        if pending is None:
            return False
        started_at = pending.get("started_at")
        if started_at is None:
            return False
        return time.time() - started_at > self._ttl_secs()

    def start_container(self, podman) -> str:
        """Create and start an ephemeral login container.

        Returns the container name. The container is NOT registered in the crew
        registry and is invisible to MCP tools.
        """
        token = secrets.token_hex(8)
        name = f"{self.container_prefix}{token}"
        podman._req(
            "POST", "/libpod/containers/create",
            json=self._container_create_payload(name),
        )
        podman.container_start(name)
        logger.info(
            "[%s] Started ephemeral login container %s", self.backend, name
        )
        return name

    def _nuke_container(self, podman, name: str) -> None:
        """Best-effort stop and remove the login container."""
        if not name.startswith(self.container_prefix):
            logger.warning(
                "[%s] Refusing to nuke non-login container: %r", self.backend, name
            )
            return
        try:
            podman.container_stop(name)
        except Exception:
            pass
        try:
            podman.container_remove(name)
        except Exception:
            pass

    def initiate(self, podman) -> dict:
        """Start the device-flow and return the login URL/code dict.

        Returns one of:
          ``{"login_url": str, "code": str | None}``  — flow started
          ``{"login_pending": True}``                 — already in progress
          ``{"error": str}``                          — hard failure

        Acquires ``self._lock`` with TOCTOU-safe guard: sets a lightweight
        sentinel immediately before releasing the lock so concurrent callers
        cannot race past the pending check.
        """
        import re

        with self._lock:
            if self._pending is not None:
                return {"login_pending": True}
            self._pending = {
                "container": None,
                "started_at": time.time(),
                "state": "starting",
            }

        # Start container
        try:
            container = self.start_container(podman)
        except Exception as e:
            logger.error("[%s] Failed to start login container: %s", self.backend, e)
            with self._lock:
                self._pending = None
            return {"error": f"Failed to start login container: {e}"}

        with self._lock:
            if self._pending is not None:
                self._pending["container"] = container
                self._pending["state"] = "started"

        # Wait for the binary
        for _ in range(10):
            try:
                check = podman.container_exec(container, ["which", self._binary_name()])
                if self._binary_name() in check:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        # Launch PTY exec
        try:
            exec_id, pty_sock, leftover = podman.container_exec_pty_stdin(
                container, self._login_cmd()
            )
        except Exception as e:
            self._nuke_container(podman, container)
            with self._lock:
                self._pending = None
            return {"error": f"Failed to start {self._binary_name()} login: {e}"}

        pty_sock.setblocking(False)

        # Run PTY read loop via the shared helper (imported from lifecycle to
        # avoid duplicating the select-loop logic)
        try:
            from lifecycle import _run_pty_login_flow  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _run_pty_login_flow  # local dev

        login_url, login_code = _run_pty_login_flow(
            pty_sock=pty_sock,
            prompt_patterns=self._prompt_patterns(),
            url_patterns=self._url_patterns(),
            code_pattern=self._code_pattern(),
            deadline_secs=45.0,
            initial_bytes=leftover,
        )

        if not login_url:
            try:
                pty_sock.close()
            except Exception:
                pass
            self._nuke_container(podman, container)
            with self._lock:
                self._pending = None
            return {
                "error": (
                    f"{self._binary_name()} did not produce a login URL within 45s."
                )
            }

        with self._lock:
            if self._pending is not None:
                self._pending["exec_id"] = exec_id

        logger.info(
            "[%s] Login flow started in %s, URL extracted", self.backend, container
        )
        return {"login_url": login_url, "code": login_code}

    def abort(self, podman) -> bool:
        """Abort an in-progress flow, if any.

        Nuke the container first, then clear ``_pending``.  Nuke-before-clear
        preserves the original ordering guarantee: if the process crashes
        between nuke and clear, a stale ``_pending`` is harmless (the
        container is already gone); clear-before-nuke would leave an orphaned
        running container.

        Returns True if a flow was aborted, False if there was nothing to abort.
        """
        with self._lock:
            pending = self._pending
            if pending is None:
                return False

        container = pending.get("container")
        if container:
            try:
                self._nuke_container(podman, container)
                logger.info(
                    "[%s] Aborted pending login in container %s",
                    self.backend, container,
                )
            except Exception as e:
                logger.warning(
                    "[%s] Could not nuke login container %s: %s",
                    self.backend, container, e,
                )
        else:
            logger.info(
                "[%s] Aborted pending login (container not yet started)", self.backend
            )

        with self._lock:
            # Only clear if the pending dict we just nuked is still current;
            # a concurrent new flow may have started between nuke and here.
            if self._pending is pending:
                self._pending = None
        return True


# ── Kiro flow ─────────────────────────────────────────────────────────────────


class KiroLoginFlow(LoginFlow):
    """Device-code login flow for the kiro-cli backend."""

    backend = "kiro"
    container_prefix = _GA_LOGIN_CONTAINER_PREFIX
    image_key = "kc_base_image"

    def _binary_name(self) -> str:
        return "kiro-cli"

    def _login_cmd(self) -> list[str]:
        cmd = ["kiro-cli", "login", "--use-device-flow"]
        if cfg.kiro_license:
            cmd += ["--license", cfg.kiro_license]
        return cmd

    def _prompt_patterns(self) -> list:
        import re
        return [
            (re.compile(r"Select login method"), b"\n"),
            (
                re.compile(r"Start URL"),
                (cfg.kiro_identity_provider.rstrip("/") + "/\n").encode(),
            ),
            (re.compile(r"Region"), (cfg.kiro_region + "\n").encode()),
        ]

    def _url_patterns(self) -> list:
        import re
        return [
            re.compile(r"Open this URL[:\s]+(https?://\S+)"),
            re.compile(r"(https?://\S+user_code=\S+)"),
        ]

    def _code_pattern(self):
        import re
        return re.compile(r"(?:user_code=|[Cc]ode[:\s]+)([A-Z0-9-]{4,})")

    def _ttl_secs(self) -> float:
        return _KIRO_LOGIN_TTL_SECS

    def auth_exists(self) -> bool:
        try:
            from lifecycle import _read_auth_file  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _read_auth_file  # local dev
        return bool(_read_auth_file())

    def write_auth(self, podman, container: str, auth_b64: str) -> None:
        try:
            from lifecycle import _write_auth_file  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _write_auth_file  # local dev
        _write_auth_file(auth_b64)

    def inject_auth(self, podman, container: str) -> None:
        try:
            from lifecycle import _inject_auth  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _inject_auth  # local dev
        _inject_auth(podman, container, "")  # auth_b64 read from file in inject_auth

    def poll(self, podman):
        try:
            from lifecycle import _read_auth_from_crew  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _read_auth_from_crew  # local dev
        container = self._pending.get("container") if self._pending else None
        if not container:
            return None
        return _read_auth_from_crew(podman, container)

    def _container_create_payload(self, name: str) -> dict:
        return {
            "name": name,
            "image": cfg.kc_base_image,
            "netns": {"nsmode": "bridge"},
            "Networks": {GA_STARBOARD_NETWORK: {}},
        }


# ── Claude flow ───────────────────────────────────────────────────────────────


class ClaudeLoginFlow(LoginFlow):
    """Device-code OAuth login flow for the Claude backend."""

    backend = "claude"
    container_prefix = _GA_CLAUDE_LOGIN_CONTAINER_PREFIX
    image_key = "kc_image"

    def _binary_name(self) -> str:
        return "claude"

    def _login_cmd(self) -> list[str]:
        return ["claude", "auth", "login"]

    def _prompt_patterns(self) -> list:
        return []  # Claude auth login is non-interactive; no prompts to answer

    def _url_patterns(self) -> list:
        import re
        return [
            re.compile(r"Please open the following URL in your browser:\s*(https?://\S+)"),
            re.compile(r"(https?://(?:claude\.ai|console\.anthropic\.com)\S+)"),
            re.compile(r"(https?://\S+)"),
        ]

    def _code_pattern(self):
        import re
        return re.compile(r"[Cc]ode[:\s]+([A-Z0-9-]{4,})")

    def _ttl_secs(self) -> float:
        return _CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS

    def auth_exists(self) -> bool:
        try:
            from lifecycle import _claude_auth_exists  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _claude_auth_exists  # local dev
        return _claude_auth_exists()

    def write_auth(self, podman, container: str, auth_b64: str) -> None:
        try:
            from lifecycle import _write_claude_auth_file  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _write_claude_auth_file  # local dev
        _write_claude_auth_file(auth_b64)

    def inject_auth(self, podman, container: str) -> None:
        try:
            from lifecycle import _inject_claude_auth  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _inject_claude_auth  # local dev
        _inject_claude_auth(podman, container)

    def poll(self, podman) -> bytes | None:
        try:
            from lifecycle import _poll_claude_login_container  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _poll_claude_login_container  # local dev
        container = self._pending.get("container") if self._pending else None
        if not container:
            return None
        return _poll_claude_login_container(podman, container)

    def submit_code(self, code: str) -> dict:
        """Write the user's pasted code to the pending PTY.

        Returns ``{"ok": True}`` on success, or ``{"error": "..."}`` on failure.
        """
        with self._lock:
            pending = self._pending
            if pending is None or pending.get("state") not in (
                "awaiting_code", "code_submitted"
            ):
                return {"error": "no_pending"}
            if pending["state"] == "code_submitted":
                return {"error": "already_submitted"}
            sock = pending.get("pty_sock")
            if sock is None:
                return {"error": "no_pending"}
            try:
                sock.sendall((code + "\n").encode())
            except Exception as e:
                logger.warning(
                    "[claude] Could not write login code to PTY: %s", type(e).__name__
                )
                return {"error": "pty_write_failed"}
            pending["state"] = "code_submitted"
            pending["code_submitted_at"] = time.time()
        return {"ok": True}

    def _is_code_expired(self) -> bool:
        """True when the in-progress code exchange has exceeded its deadline."""
        with self._lock:
            pending = self._pending
        if pending is None:
            return False
        state = pending.get("state")
        now = time.time()
        if state == "awaiting_code":
            started = pending.get("started_at")
            return (
                started is not None
                and now - started > _CLAUDE_LOGIN_APPROVAL_DEADLINE_SECS
            )
        if state == "code_submitted":
            submitted = pending.get("code_submitted_at")
            return (
                submitted is not None
                and now - submitted > _CLAUDE_LOGIN_CODE_DEADLINE_SECS
            )
        return False

    def is_expired(self) -> bool:
        return self._is_code_expired()

    def _container_create_payload(self, name: str) -> dict:
        return {
            "name": name,
            "image": cfg.kc_image,
            "netns": {"nsmode": "bridge"},
            "Networks": {GA_STARBOARD_NETWORK: {}},
        }


# ── Codex flow ────────────────────────────────────────────────────────────────


class CodexLoginFlow(LoginFlow):
    """Device-code OAuth login flow for the Codex (OpenAI) backend."""

    backend = "codex"
    container_prefix = _GA_CODEX_LOGIN_CONTAINER_PREFIX
    image_key = "kc_image"

    def _binary_name(self) -> str:
        return "codex-acp"

    def _login_cmd(self) -> list[str]:
        return ["codex-acp", "login"]

    def _prompt_patterns(self) -> list:
        return []  # Codex login is non-interactive

    def _url_patterns(self) -> list:
        import re
        return [
            re.compile(r"(https?://\S+)"),
        ]

    def _code_pattern(self):
        import re
        return re.compile(r"[Cc]ode[:\s]+([A-Z0-9-]{4,})")

    def _ttl_secs(self) -> float:
        return _CODEX_LOGIN_TTL_SECS

    def auth_exists(self) -> bool:
        try:
            from lifecycle import _codex_auth_exists  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _codex_auth_exists  # local dev
        return _codex_auth_exists()

    def write_auth(self, podman, container: str, auth_b64: str) -> None:
        try:
            from lifecycle import _write_codex_auth_file  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _write_codex_auth_file  # local dev
        _write_codex_auth_file(auth_b64)

    def inject_auth(self, podman, container: str) -> None:
        try:
            from lifecycle import _inject_codex_auth  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _inject_codex_auth  # local dev
        _inject_codex_auth(podman, container)

    def poll(self, podman) -> bytes | None:
        try:
            from lifecycle import _poll_codex_login_container  # container
        except ModuleNotFoundError:
            from transport.lifecycle import _poll_codex_login_container  # local dev
        container = self._pending.get("container") if self._pending else None
        if not container:
            return None
        return _poll_codex_login_container(podman, container)

    def _container_create_payload(self, name: str) -> dict:
        return {
            "name": name,
            "image": cfg.kc_image,
            "netns": {"nsmode": "bridge"},
            "Networks": {GA_STARBOARD_NETWORK: {}},
        }


# ── Module-level singletons ───────────────────────────────────────────────────
# One instance per backend; each holds the in-progress flow state.
# After TRN-240 task 5.3, lifecycle.py's module-level _login_pending /
# _claude_login_pending / _codex_login_pending become properties forwarding
# to these singletons' .state attribute.

KIRO_FLOW = KiroLoginFlow()
CLAUDE_FLOW = ClaudeLoginFlow()
CODEX_FLOW = CodexLoginFlow()

#: All three flows — useful for ``for flow in ALL_FLOWS: flow.abort(podman)``
ALL_FLOWS: list[LoginFlow] = [KIRO_FLOW, CLAUDE_FLOW, CODEX_FLOW]
