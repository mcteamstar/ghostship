"""LoginFlow class hierarchy and HTTP handlers for ACP backend auth flows.

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

HTTP handlers (extracted from server.py, TRN-242)
--------------------------------------------------
The ten Starlette route handlers for the three login/logout flows live here
alongside the ``LoginFlow`` singletons they delegate to:

  kiro:   _handle_login_post, _handle_login_get
  claude: _handle_claude_login_post, _handle_claude_login_get,
          _handle_claude_login_code_post
  codex:  _handle_codex_login_post, _handle_codex_login_get

All three ``/logout/{backend}`` routes call ``_logout`` (TRN-258).

Three backend-check helpers used only by the handlers also live here:
  _warn_inert_backend_settings, _backend_enabled, _backend_not_enabled_message

``server.py`` imports all thirteen names for its ``BearerAuthMiddleware`` route
table; it no longer defines them itself.
"""

from __future__ import annotations

import json
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


# ── HTTP login/logout handler dependencies (TRN-242) ──────────────────────────
# The ten login/logout Starlette handlers and the three backend helpers moved
# here from server.py alongside the LoginFlow singletons they delegate to. These
# module-level imports cover their non-lifecycle dependencies; lifecycle names
# are resolved lazily through _lc() (login must not import lifecycle at module
# load — lifecycle imports login, so the dependency runs one way).
import dataclasses

from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse, JSONResponse

try:
    import security as _security  # container: flat /app/
except ModuleNotFoundError:
    from transport import security as _security  # local dev

try:
    from auth import _request_source  # container: flat /app/
except ModuleNotFoundError:
    from transport.auth import _request_source  # local dev

try:
    from registry import registry  # container: flat /app/
except ModuleNotFoundError:
    from transport.registry import registry  # local dev

try:
    from podman import _get_podman  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import _get_podman  # local dev

try:
    from config import inert_backend_settings, _ACP_BACKEND_VALUES  # container: flat /app/
except ImportError:
    from transport.config import inert_backend_settings, _ACP_BACKEND_VALUES  # local dev

try:
    from credentials import CredentialStore  # container: flat /app/
except ImportError:
    from transport.credentials import CredentialStore  # local dev

# Credential store — resolved per-call in _warn_inert_backend_settings
# (TRN-233 task 2.1). No module-level credential globals remain.
_cred_store = CredentialStore()

_lifecycle_mod = None


def _lc():
    """Return the fully-loaded lifecycle module, importing it on first use.

    login is imported BY lifecycle, so importing lifecycle at login's module
    load would cycle. By the time any HTTP handler runs, lifecycle is fully
    loaded, so a lazy accessor is safe. Mirrors the call-time lifecycle imports
    already used inside the LoginFlow subclasses.
    """
    global _lifecycle_mod
    if _lifecycle_mod is None:
        try:
            import lifecycle as _lc_mod  # container: flat /app/
        except ModuleNotFoundError:
            from transport import lifecycle as _lc_mod  # local dev
        _lifecycle_mod = _lc_mod
    return _lifecycle_mod


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

    def initiate(self, podman, pending_extra: dict | None = None) -> dict:
        """Start the device-flow and return the login URL/code dict.

        ``pending_extra`` is merged into the pending state before the login
        command is built, so subclasses can read per-flow options (e.g. the
        kiro method/provider) from ``self._pending`` in ``_login_cmd``.

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
            pending = {
                "container": None,
                "started_at": time.time(),
                "state": "starting",
                **(pending_extra or {}),
            }
            self._pending = pending

        # Start container
        try:
            container = self.start_container(podman)
        except Exception as e:
            logger.error("[%s] Failed to start login container: %s", self.backend, e)
            with self._lock:
                if self._pending is pending:
                    self._pending = None
            return {"error": f"Failed to start login container: {e}"}

        # Identity, not "is not None": an abort during start_container clears
        # _pending, and a new flow may have taken its place. Only record the
        # container against the dict this call created.
        with self._lock:
            cancelled = self._pending is not pending
            if not cancelled:
                pending["container"] = container
                pending["state"] = "started"
        if cancelled:
            logger.info("[%s] Login cancelled while starting %s", self.backend, container)
            self._nuke_container(podman, container)
            return {"error": "cancelled"}

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
                if self._pending is pending:
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
                current = self._pending is pending
                if current:
                    self._pending = None
            if not current:
                return {"error": "cancelled"}
            return {
                "error": (
                    f"{self._binary_name()} did not produce a login URL within 45s."
                )
            }

        # A logout may have cancelled this flow during the PTY read. Return no
        # URL for it: the container is gone and nothing can be stored.
        with self._lock:
            cancelled = self._pending is not pending
            if not cancelled:
                pending["exec_id"] = exec_id
        if cancelled:
            try:
                pty_sock.close()
            except Exception:
                pass
            self._nuke_container(podman, container)
            logger.info("[%s] Login cancelled while waiting for a URL", self.backend)
            return {"error": "cancelled"}

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

    def commit_if_current(self, pending: dict, store_fn) -> bool:
        """Store a completed login's credential only if its flow is still live.

        *pending* is the dict a completion path captured before polling the
        login container. Under the lock, if ``_pending`` is still that dict,
        run ``store_fn`` and clear ``_pending`` in the same critical section, so
        an abort cannot land between the check and the store. If ``store_fn``
        raises, ``_pending`` is left in place so the caller can retry.

        Returns False when the flow was cancelled or replaced since *pending*
        was captured. The caller must then discard its result and remove
        ``pending["container"]``.
        """
        with self._lock:
            if self._pending is not pending:
                return False
            store_fn()
            self._pending = None
            return True


def _nuke_pending_container(flow: LoginFlow, podman, pending: dict) -> None:
    """Best-effort removal of the login container a completed or cancelled flow owned."""
    container = pending.get("container")
    if container:
        flow._nuke_container(podman, container)


# ── Kiro flow ─────────────────────────────────────────────────────────────────


class KiroLoginFlow(LoginFlow):
    """Device-code login flow for the kiro-cli backend."""

    backend = "kiro"
    container_prefix = _GA_LOGIN_CONTAINER_PREFIX
    image_key = "kc_base_image"

    def _binary_name(self) -> str:
        return "kiro-cli"

    def initiate(
        self, podman, method: str | None = None, provider: dict | None = None
    ) -> dict:
        """Start a kiro device flow for *method* (builder-id or identity-center).

        With no *method*, identity-center is used when KIRO_IDENTITY_PROVIDER and
        KIRO_REGION are both configured, else builder-id. For identity-center a
        missing *provider* falls back to the configured start URL and region.
        """
        if method is None:
            method = (
                "identity-center"
                if cfg.kiro_identity_provider and cfg.kiro_region
                else "builder-id"
            )
        if method == "identity-center":
            provider = provider or {
                "start_url": cfg.kiro_identity_provider,
                "region": cfg.kiro_region,
            }
        else:
            provider = None
        return super().initiate(
            podman, pending_extra={"method": method, "provider": provider}
        )

    def _provider(self) -> dict | None:
        pending = self._pending
        return pending.get("provider") if pending else None

    def _login_cmd(self) -> list[str]:
        # --license picks the login method, not a subscription tier: pro is
        # Identity Center, free is Builder ID / social. Passing it explicitly
        # skips kiro-cli's "Select login method" menu.
        cmd = ["kiro-cli", "login", "--use-device-flow"]
        provider = self._provider()
        if provider:
            cmd += [
                "--license", "pro",
                "--identity-provider", provider["start_url"],
                "--region", provider["region"],
            ]
        else:
            cmd += ["--license", "free"]
        return cmd

    def _prompt_patterns(self) -> list:
        # --license skips the method menu (kept as a fallback). With
        # --identity-provider/--region, kiro-cli still shows the Start URL and
        # Region prompts but pre-fills them, so a bare Enter accepts the value;
        # typing it again would append to the pre-filled text.
        import re
        patterns = [(re.compile(r"Select login method"), b"\n")]
        if self._provider():
            patterns += [
                (re.compile(r"Start URL"), b"\n"),
                (re.compile(r"Region"), b"\n"),
            ]
        return patterns

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


# ──────────────────────────────────────────────────────────────────────────────
# HTTP login/logout handlers (moved from server.py, TRN-242)
# Ten Starlette route handlers + three backend helpers. server.py re-exports
# these names and wires them into BearerAuthMiddleware; lifecycle names are
# reached through _lc(). See the dependency note above the _lc() accessor.
# ──────────────────────────────────────────────────────────────────────────────

def _warn_inert_backend_settings() -> None:
    """Log one warning per credential or stored credential that belongs to a
    disabled backend. Also warns about *_BASE_URL settings for disabled backends.

    Called once from the startup path. Names only; values are never logged.
    Updated for TRN-233: checks the credential store for each disabled backend
    rather than Podman-secret-backed module-level globals.
    """
    status = _cred_store.status()
    enabled = frozenset(_enabled_backends())
    # Per-backend BASE_URL settings that belong only to non-kiro backends.
    _BASE_URL_SETTINGS: dict[str, str] = {
        "claude": "ANTHROPIC_BASE_URL",
        "codex": "OPENAI_BASE_URL",
    }
    _base_url_values: dict[str, str] = {
        "claude": cfg.anthropic_base_url,
        "codex": cfg.openai_base_url,
    }
    for backend, info in status.items():
        if backend == "kiro":
            continue
        if backend in enabled:
            continue
        # Stored credential for a disabled backend
        if info["configured"]:
            logger.warning(
                "%s has a stored credential (method=%s) but its backend is not "
                "enabled in GA_CREW_AGENT; it has no effect.",
                backend,
                info.get("method"),
            )
        # BASE_URL setting for a disabled backend
        if _base_url_values.get(backend):
            logger.warning(
                "%s is set but its backend (%s) is not enabled in "
                "GA_CREW_AGENT; it has no effect.",
                _BASE_URL_SETTINGS[backend],
                backend,
            )


def _enabled_backends() -> tuple[str, ...]:
    """The enabled backends in GA_CREW_AGENT order — so the first entry is the
    transport default — with kiro (always enabled; bundled in every crew image)
    appended when not listed."""
    names: list[str] = []
    for name in cfg.ga_crew_agent.split(","):
        name = name.strip().lower()
        if name and name not in names:
            names.append(name)
    if "kiro" not in names:
        names.append("kiro")
    return tuple(names)


def _backend_enabled(backend: str) -> bool:
    """True when ``backend`` is enabled. Kiro always is (bundled in every crew
    image); others must be listed in GA_CREW_AGENT."""
    return backend in _enabled_backends()


def _backend_not_enabled_message(backend: str) -> str:
    if backend not in _ACP_BACKEND_VALUES:
        return (
            f"'{backend}' is not a known backend. Valid backends: "
            f"{', '.join(sorted(_ACP_BACKEND_VALUES))}."
        )
    return (
        f"The {backend} backend is not enabled on this transport. Add {backend} to "
        f"backends.default in ghostship.yaml, then re-run `ghostship install`."
    )


async def _handle_login_post(
    request: Request, method: str | None = None, provider: dict | None = None
) -> Response:
    """POST /login — initiate kiro-cli device auth via an ephemeral temp container.

    State machine guard:
      - 409 if ga-kiro-auth already exists and is non-empty (already authenticated)
      - 409 if a login flow is already pending

    Delegates to _lc()._initiate_login() for the actual container start and PTY flow.
    Returns the URL and code immediately so the operator can open the browser.
    """
    if _lc()._read_auth_file():
        return PlainTextResponse(
            "Already authenticated. Run 'ghostship auth logout kiro' first.",
            status_code=409,
        )
    if KIRO_FLOW.state is not None:
        return PlainTextResponse(
            "Login already in progress. Run 'ghostship auth logout kiro' to cancel, or poll GET /login for status.",
            status_code=409,
        )

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    result = _lc()._initiate_login(podman, method=method, provider=provider)

    if result.get("login_pending"):
        return PlainTextResponse(
            "Login already in progress. Run 'ghostship auth logout kiro' to cancel, or poll GET /login for status.",
            status_code=409,
        )
    if "error" in result:
        return PlainTextResponse(result["error"], status_code=500)

    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


async def _handle_login_get(request: Request) -> Response:
    """GET /login — poll whether the kiro-cli device auth flow has completed.

    Returns {status: "pending"} while the browser flow is in progress.
    On completion: writes ga-kiro-auth, injects auth into all running crews,
    nukes the temp container, clears _login_pending, returns {status: "complete"}.
    Returns 404 if no login flow is in progress.
    """
    pending = KIRO_FLOW.state

    if pending is None:
        return PlainTextResponse("No login in progress.", status_code=404)

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    auth_b64 = _lc()._read_auth_from_crew(podman, pending["container"])
    if not auth_b64:
        return JSONResponse({"status": "pending"})

    # ── Auth complete ─────────────────────────────────────────────────────────
    # The legacy file write and the credential-store put run inside the flow's
    # commit, so a logout that cancels this flow first stores nothing.
    _provider = pending.get("provider")
    _method = "identity-center" if _provider else "builder-id"

    def _store() -> None:
        _lc()._write_auth_file(auth_b64)
        logger.info("ga-kiro-auth written after login completion")
        # Store via the credential store (TRN-233). The auth_b64 is the SQLite
        # row data; method is builder-id (default) unless identity-center was used.
        try:
            _cred_store.put(
                "kiro", _method,
                auth_b64.encode("utf-8") if isinstance(auth_b64, str) else auth_b64,
                provider=_provider,
            )
            logger.info("Stored kiro %s credential in credential store", _method)
        except Exception as e:
            logger.warning("Could not store kiro credential in credential store: %s", e)

    try:
        committed = KIRO_FLOW.commit_if_current(pending, _store)
    except Exception as e:
        # Keep the login container and pending state so the next poll can retry,
        # rather than discarding the only copy of the credential.
        logger.error("Could not write ga-kiro-auth: %s", e)
        _security.audit_auth_event(
            action="login", outcome="failure", account="academy",
            source=_request_source(request), emit=logger.info,
        )
        return JSONResponse(
            {"status": "error",
             "error": "Login completed but the credential could not be saved; poll again to retry."},
            status_code=500,
        )
    if not committed:
        _nuke_pending_container(KIRO_FLOW, podman, pending)
        return JSONResponse({"status": "cancelled"})

    # Inject into running kiro crews only. Since TRN-259 a transport can run
    # claude and codex crews too; an entry with no acp_backend field is kiro
    # (matches Crew.from_dict's default).
    with registry:
        _running_crews = {
            cid: info
            for cid, info in registry._reg["crews"].items()
            if info.get("status") == "running"
            and info.get("acp_backend", "kiro") == "kiro"
        }
    for cid, info in _running_crews.items():
        try:
            _lc()._inject_auth(podman, info["container"], auth_b64)
            logger.info("Injected fresh auth into running crew %s", cid)
        except Exception as e:
            logger.warning("Could not inject auth into crew %s: %s", cid, e)

    _nuke_pending_container(KIRO_FLOW, podman, pending)

    _security.audit_auth_event(
        action="login", outcome="success", account="academy",
        source=_request_source(request),
        emit=logger.info,
    )
    return JSONResponse({"status": "complete"})


async def _handle_claude_login_post(request: Request) -> Response:
    """POST /login/claude — initiate Claude OAuth device-code flow.

    Three-state machine guard:
      - 409 if ga-claude-auth already exists (already authenticated)
      - 409 if a Claude login flow is already in progress
      - Calls _lc()._initiate_claude_login, returns {"login_url", "code"}

    Requires claude to be an enabled backend (GA_CREW_AGENT), whether or
    not it is the default; returns 400 otherwise.
    """
    if not _backend_enabled("claude"):
        return PlainTextResponse(_backend_not_enabled_message("claude"), status_code=400)

    if _lc()._claude_auth_exists():
        return PlainTextResponse(
            "Already authenticated. Run 'ghostship auth logout claude' first.",
            status_code=409,
        )
    if CLAUDE_FLOW.state is not None:
        return PlainTextResponse(
            "Claude login already in progress. Run 'ghostship auth logout claude' to cancel, or poll GET /login/claude for status.",
            status_code=409,
        )

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    result = _lc()._initiate_claude_login(podman)

    if result.get("login_pending"):
        return PlainTextResponse(
            "Claude login already in progress. Run 'ghostship auth logout claude' to cancel, or poll GET /login/claude for status.",
            status_code=409,
        )
    if "error" in result:
        return PlainTextResponse(result["error"], status_code=500)

    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


async def _handle_claude_login_get(request: Request) -> Response:
    """GET /login/claude — poll whether the Claude OAuth flow has completed.

    Returns {"status": "pending", "login_url": ...} while waiting.
    On completion: tars ~/.claude/ from the login container, writes ga-claude-auth
    (mode 0600), nukes the login container, clears _claude_login_pending, and
    returns {"status": "complete"}.
    Returns 404 if no Claude login flow is in progress.
    """
    pending = CLAUDE_FLOW.state

    if pending is None:
        return PlainTextResponse("No Claude login in progress.", status_code=404)

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    # A submitted code that never completed the exchange abandons the flow.
    if CLAUDE_FLOW.is_expired():
        CLAUDE_FLOW.abort(podman)
        _security.audit_auth_event(
            action="login", outcome="failure", account="claude",
            source=_request_source(request),
            emit=logger.info,
        )
        return JSONResponse({"status": "expired"}, status_code=410)

    # Poll the login container for the completed Claude credential.
    tar_bytes = CLAUDE_FLOW.poll(podman)
    if not tar_bytes:
        return JSONResponse({
            "status": "pending",
            "login_url": pending.get("login_url"),
        })

    # ── Auth complete — store via credential store + write legacy ga-claude-auth ─
    # Both writes run inside the flow's commit, so a logout that cancels this
    # flow first stores nothing.
    def _store() -> None:
        _lc()._write_claude_auth_file(tar_bytes)
        logger.info("ga-claude-auth written after Claude login completion")
        # Store via the credential store (TRN-233). The payload is the tar bytes;
        # storing base64 of the raw tar mirrors the existing oauth archive convention.
        try:
            import base64 as _base64
            _cred_store.put("claude", "oauth", _base64.b64encode(tar_bytes))
            logger.info("Stored claude OAuth credential in credential store")
        except Exception as e:
            logger.warning("Could not store claude credential in credential store: %s", e)

    try:
        committed = CLAUDE_FLOW.commit_if_current(pending, _store)
    except Exception as e:
        # Keep the login container and pending state so the next poll can retry,
        # rather than discarding the only copy of the credential.
        logger.error("Could not write ga-claude-auth: %s", e)
        _security.audit_auth_event(
            action="login", outcome="failure", account="claude",
            source=_request_source(request), emit=logger.info,
        )
        return JSONResponse(
            {"status": "error",
             "error": "Login completed but the credential could not be saved; poll again to retry."},
            status_code=500,
        )
    # Close the PTY socket (the flow does not) and nuke the temp container,
    # whether the flow completed or was cancelled while we polled.
    pty_sock = pending.get("pty_sock")
    if pty_sock is not None:
        try:
            pty_sock.close()
        except Exception:
            pass
    _nuke_pending_container(CLAUDE_FLOW, podman, pending)
    if not committed:
        return JSONResponse({"status": "cancelled"})

    _security.audit_auth_event(
        action="login", outcome="success", account="claude",
        source=_request_source(request),
        emit=logger.info,
    )
    return JSONResponse({"status": "complete"})


async def _handle_claude_login_code_post(request: Request) -> Response:
    """POST /login/claude/code — deliver the pasted Claude authorisation code.

    Body: {"code": "<code>"}. The code is written to the pending login's PTY so
    the CLI can complete the token exchange. Poll GET /login/claude afterwards.

    Returns 202 once the code is written, 400 for a malformed body, 404 when no
    flow is awaiting a code, 409 when a code was already submitted, and 500 when
    the PTY closed before the write. The code is never logged or echoed.
    Requires claude to be an enabled backend; returns 400 otherwise. That check
    runs before the body is parsed or the pending flow is looked up.
    """
    if not _backend_enabled("claude"):
        return JSONResponse({"error": _backend_not_enabled_message("claude")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    code = body.get("code") if isinstance(body, dict) else None
    if not isinstance(code, str) or not code.strip():
        return JSONResponse({"error": "'code' must be a non-empty string."}, status_code=400)

    result = _lc()._submit_claude_login_code(code.strip())
    error = result.get("error")
    if error == "no_pending":
        return JSONResponse({"error": "No Claude login is awaiting a code."}, status_code=404)
    if error == "already_submitted":
        return JSONResponse(
            {"error": "A code was already submitted; poll GET /login/claude."},
            status_code=409,
        )
    if error:
        return JSONResponse({"error": "The login session closed before the code was written."},
                            status_code=500)
    return JSONResponse({"status": "submitted"}, status_code=202)


async def _handle_codex_login_post(request: Request) -> Response:
    """POST /login/codex — initiate Codex OAuth/device login flow.

    Three-state machine guard (mirrors POST /login/claude):
      - 409 if ga-codex-auth already exists (already authenticated)
      - 409 if a Codex login flow is already in progress
      - Calls _lc()._initiate_codex_login, returns {"login_url", "code"}

    Requires codex to be an enabled backend (GA_CREW_AGENT), whether or
    not it is the default; returns 400 otherwise.
    """
    if not _backend_enabled("codex"):
        return PlainTextResponse(_backend_not_enabled_message("codex"), status_code=400)

    if _lc()._codex_auth_exists():
        return PlainTextResponse(
            "Already authenticated. Run 'ghostship auth logout codex' first.",
            status_code=409,
        )
    if CODEX_FLOW.state is not None:
        return PlainTextResponse(
            "Codex login already in progress. Run 'ghostship auth logout codex' to cancel, or poll GET /login/codex for status.",
            status_code=409,
        )

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    result = _lc()._initiate_codex_login(podman)

    if result.get("login_pending"):
        return PlainTextResponse(
            "Codex login already in progress. Run 'ghostship auth logout codex' to cancel, or poll GET /login/codex for status.",
            status_code=409,
        )
    if "error" in result:
        return PlainTextResponse(result["error"], status_code=500)

    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


async def _handle_codex_login_get(request: Request) -> Response:
    """GET /login/codex — poll whether the Codex OAuth flow has completed.

    Returns {"status": "pending", "login_url": ...} while waiting.
    On completion: tars ~/.codex/ from the login container, writes ga-codex-auth
    (mode 0600), nukes the login container, clears _codex_login_pending, and
    returns {"status": "complete"}.
    Returns 404 if no Codex login flow is in progress.
    """
    pending = CODEX_FLOW.state

    if pending is None:
        return PlainTextResponse("No Codex login in progress.", status_code=404)

    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)

    # Poll the login container for completed ~/.codex/ credentials.
    tar_bytes = CODEX_FLOW.poll(podman)
    if not tar_bytes:
        return JSONResponse({
            "status": "pending",
            "login_url": pending.get("login_url"),
        })

    # ── Auth complete — write ga-codex-auth ───────────────────────────────────
    # The write runs inside the flow's commit, so a logout that cancels this
    # flow first stores nothing.
    def _store() -> None:
        _lc()._write_codex_auth_file(tar_bytes)
        logger.info("ga-codex-auth written after Codex login completion")

    try:
        committed = CODEX_FLOW.commit_if_current(pending, _store)
    except Exception as e:
        # Keep the login container and pending state so the next poll can retry,
        # rather than discarding the only copy of the credential.
        logger.error("Could not write ga-codex-auth: %s", e)
        _security.audit_auth_event(
            action="login", outcome="failure", account="codex",
            source=_request_source(request), emit=logger.info,
        )
        return JSONResponse(
            {"status": "error",
             "error": "Login completed but the credential could not be saved; poll again to retry."},
            status_code=500,
        )
    _nuke_pending_container(CODEX_FLOW, podman, pending)
    if not committed:
        return JSONResponse({"status": "cancelled"})

    _security.audit_auth_event(
        action="login", outcome="success", account="codex",
        source=_request_source(request),
        emit=logger.info,
    )
    return JSONResponse({"status": "complete"})


# ── TRN-233: new /login/{backend}/{method} and /logout/{backend} routes ───────
# These replace the old bare /login, /logout, /login/claude, etc. paths.
# All routes require bearer auth (registered in BearerAuthMiddleware.routes).


# ── GET /login/{backend} — status for any backend ────────────────────────────

async def _handle_login_kiro_get(request: Request) -> Response:
    """GET /login/kiro — status of the kiro credential and any pending flow.

    When a flow is in progress, also polls the login container for completion
    and stores the result via the credential store (TRN-233). Mirrors the
    original _handle_login_get polling cycle.
    """
    pending = KIRO_FLOW.state
    # Spec (backend-credentials §GET): for kiro, also return the configured
    # Identity Center start_url/region when set, so the CLI can offer them
    # as defaults. Non-secret config — never a credential value.
    ic = None
    if cfg.kiro_identity_provider or cfg.kiro_region:
        ic = {
            "start_url": cfg.kiro_identity_provider or None,
            "region": cfg.kiro_region or None,
        }
    # No flow in progress — return credential store status
    if pending is None:
        st = _cred_store.status().get("kiro", {})
        resp: dict = {
            "backend": "kiro",
            "configured": st.get("configured", False),
            "method": st.get("method"),
            "stored_at": st.get("stored_at"),
            "pending_flow": None,
        }
        if ic:
            resp["identity_center"] = ic
        return JSONResponse(resp)
    # Flow in progress — delegate to the existing polling handler
    # which also drives completion and writes ga-kiro-auth. Keep the Identity
    # Center defaults on its JSON responses too, or the CLI loses them while a
    # stale flow is pending.
    poll = await _handle_login_get(request)
    if ic and isinstance(poll, JSONResponse):
        body = json.loads(poll.body)
        body["identity_center"] = ic
        return JSONResponse(body, status_code=poll.status_code)
    return poll


async def _handle_login_claude_get_new(request: Request) -> Response:
    """GET /login/claude — status of the claude credential and any pending flow.

    When a flow is in progress, delegates to the polling handler which drives
    completion and stores the result. When no flow is running, returns status
    from the credential store.
    """
    pending = CLAUDE_FLOW.state
    if pending is None:
        st = _cred_store.status().get("claude", {})
        return JSONResponse({
            "backend": "claude",
            "configured": st.get("configured", False),
            "method": st.get("method"),
            "stored_at": st.get("stored_at"),
            "pending_flow": None,
        })
    # Flow in progress — delegate to the existing claude poll handler
    return await _handle_claude_login_get(request)


async def _handle_login_codex_get_new(request: Request) -> Response:
    """GET /login/codex — status of the codex credential and any pending flow.

    When a flow is in progress, delegates to the existing codex poll handler.
    """
    pending = CODEX_FLOW.state
    if pending is None:
        st = _cred_store.status().get("codex", {})
        return JSONResponse({
            "backend": "codex",
            "configured": st.get("configured", False),
            "method": st.get("method"),
            "stored_at": st.get("stored_at"),
            "pending_flow": None,
        })
    return await _handle_codex_login_get(request)


# ── POST /login/kiro/* ────────────────────────────────────────────────────────

async def _handle_login_kiro_api_key_post(request: Request) -> Response:
    """POST /login/kiro/api-key — store a pasted Kiro API key."""
    if not _backend_enabled("kiro"):
        return JSONResponse({"error": _backend_not_enabled_message("kiro")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    secret = body.get("secret") if isinstance(body, dict) else None
    if not isinstance(secret, str) or not secret.strip():
        return JSONResponse({"error": "'secret' must be a non-empty string."}, status_code=400)
    _cred_store.put("kiro", "api-key", secret.strip())
    _security.audit_auth_event(
        action="login", outcome="success", account="kiro",
        source=_request_source(request), emit=logger.info,
    )
    st = _cred_store.status().get("kiro", {})
    return JSONResponse({
        "status": "stored",
        "backend": "kiro",
        "method": "api-key",
        "stored_at": st.get("stored_at"),
    })


async def _handle_login_kiro_builder_id_post(request: Request) -> Response:
    """POST /login/kiro/builder-id — initiate kiro Builder ID device flow."""
    if not _backend_enabled("kiro"):
        return JSONResponse({"error": _backend_not_enabled_message("kiro")}, status_code=400)
    # Delegate to the existing kiro login initiation (PTY flow).
    return await _handle_login_post(request, method="builder-id")


async def _handle_login_kiro_identity_center_post(request: Request) -> Response:
    """POST /login/kiro/identity-center — initiate kiro Identity Center device flow.

    Accepts optional {start_url?, region?} in the request body;
    falls back to KIRO_IDENTITY_PROVIDER/KIRO_REGION from config.
    Returns 400 if no start_url or region is available.
    """
    if not _backend_enabled("kiro"):
        return JSONResponse({"error": _backend_not_enabled_message("kiro")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        body = {}
    body = body if isinstance(body, dict) else {}
    start_url = body.get("start_url") or cfg.kiro_identity_provider
    region = body.get("region") or cfg.kiro_region
    if not start_url or not region:
        return JSONResponse(
            {"error": "start_url and region are required for identity-center login "
             "(provide in request body or set KIRO_IDENTITY_PROVIDER/KIRO_REGION)."},
            status_code=400,
        )
    return await _handle_login_post(
        request,
        method="identity-center",
        provider={"start_url": start_url, "region": region},
    )


# ── POST /logout/kiro ─────────────────────────────────────────────────────────

# ── POST /logout/{backend} ────────────────────────────────────────────────────
# TRN-258: logout acts on the transport only. It cancels any pending login for
# the backend, then removes the stored credential and the legacy device file.
# Running crews are never touched; they keep the credential they launched with.


def _logout(backend: str, request: Request) -> Response:
    """Cancel a pending *backend* login, then remove its stored credential.

    Idempotent: returns 200 whether or not anything was pending or stored.
    Returns 500 when a credential could not be removed, or when podman is
    unavailable so a pending login could not be cancelled.
    """
    lc = _lc()
    if backend == "kiro":
        abort, legacy_path, account = lc._abort_pending_login, lc._auth_file_path(), "academy"
    elif backend == "claude":
        abort, legacy_path, account = lc._abort_claude_pending_login, lc._claude_auth_file_path(), "claude"
    else:
        abort, legacy_path, account = lc._abort_codex_pending_login, lc._codex_auth_file_path(), "codex"

    # Abort first: a pending login must not be able to store a credential after
    # this call removes it (see LoginFlow.commit_if_current). With podman down the
    # abort cannot run, but no login poll can run either, so the removal still
    # happens and the 500 below reports the pending login that was left behind.
    aborted = False
    cancel_error = None
    try:
        aborted = abort(_get_podman())
    except Exception as e:
        cancel_error = str(e)

    store_removed = legacy_removed = failed = False
    try:
        store_removed = _cred_store.delete(backend)
    except OSError as e:
        logger.error("Could not delete %s credential from store: %s", backend, e)
        failed = True
    try:
        legacy_path.unlink()
        legacy_removed = True
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.error("Could not delete legacy %s auth file: %s", backend, e)
        failed = True

    if failed:
        _security.audit_auth_event(
            action="logout", outcome="failure", account=account,
            source=_request_source(request), emit=logger.info,
        )
        return JSONResponse(
            {"status": "error", "error": "The stored credential could not be deleted."},
            status_code=500,
        )
    # Audit only a logout that removed something; a no-op logout is not an event.
    if store_removed or legacy_removed:
        _security.audit_auth_event(
            action="logout", outcome="success", account=account,
            source=_request_source(request), emit=logger.info,
        )
    if cancel_error is not None:
        logger.error("Could not cancel pending %s login: %s", backend, cancel_error)
        return JSONResponse(
            {"status": "error",
             "error": "The stored credential was removed, but a pending login could not be cancelled."},
            status_code=500,
        )
    body: dict = {"status": "logged_out"}
    if aborted:
        body["aborted_pending_login"] = True
    return JSONResponse(body)


async def _handle_logout_kiro_post(request: Request) -> Response:
    """POST /logout/kiro — cancel a pending kiro login and remove its credential."""
    return _logout("kiro", request)


# ── POST /login/claude/* ──────────────────────────────────────────────────────

async def _handle_login_claude_api_key_post(request: Request) -> Response:
    """POST /login/claude/api-key — store a pasted Anthropic API key."""
    if not _backend_enabled("claude"):
        return JSONResponse({"error": _backend_not_enabled_message("claude")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    secret = body.get("secret") if isinstance(body, dict) else None
    if not isinstance(secret, str) or not secret.strip():
        return JSONResponse({"error": "'secret' must be a non-empty string."}, status_code=400)
    _cred_store.put("claude", "api-key", secret.strip())
    _security.audit_auth_event(
        action="login", outcome="success", account="claude",
        source=_request_source(request), emit=logger.info,
    )
    st = _cred_store.status().get("claude", {})
    return JSONResponse({
        "status": "stored",
        "backend": "claude",
        "method": "api-key",
        "stored_at": st.get("stored_at"),
    })


async def _handle_login_claude_setup_token_post(request: Request) -> Response:
    """POST /login/claude/setup-token — store a pasted claude setup-token."""
    if not _backend_enabled("claude"):
        return JSONResponse({"error": _backend_not_enabled_message("claude")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    secret = body.get("secret") if isinstance(body, dict) else None
    if not isinstance(secret, str) or not secret.strip():
        return JSONResponse({"error": "'secret' must be a non-empty string."}, status_code=400)
    _cred_store.put("claude", "setup-token", secret.strip())
    _security.audit_auth_event(
        action="login", outcome="success", account="claude",
        source=_request_source(request), emit=logger.info,
    )
    st = _cred_store.status().get("claude", {})
    return JSONResponse({
        "status": "stored",
        "backend": "claude",
        "method": "setup-token",
        "stored_at": st.get("stored_at"),
    })


async def _handle_login_claude_oauth_post(request: Request) -> Response:
    """POST /login/claude/oauth — initiate Claude authorisation-code flow.

    Starting a flow no longer returns 409 when a credential already exists
    (TRN-233 design §3) — the store.put replaces on completion.
    """
    if not _backend_enabled("claude"):
        return JSONResponse({"error": _backend_not_enabled_message("claude")}, status_code=400)
    if CLAUDE_FLOW.state is not None:
        return JSONResponse(
            {"error": "Claude login already in progress. Run 'ghostship auth logout claude' to cancel, or poll GET /login/claude."},
            status_code=409,
        )
    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)
    result = _lc()._initiate_claude_login(podman)
    if result.get("login_pending"):
        return JSONResponse(
            {"error": "Claude login already in progress. Run 'ghostship auth logout claude' to cancel, or poll GET /login/claude."},
            status_code=409,
        )
    if "error" in result:
        return JSONResponse({"error": result["error"]}, status_code=500)
    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


async def _handle_login_claude_oauth_code_post(request: Request) -> Response:
    """POST /login/claude/oauth/code — submit the OAuth authorisation code."""
    return await _handle_claude_login_code_post(request)


# ── POST /logout/claude ───────────────────────────────────────────────────────

async def _handle_logout_claude_post_new(request: Request) -> Response:
    """POST /logout/claude — cancel a pending claude login and remove its credential."""
    return _logout("claude", request)


# ── POST /login/codex/* ───────────────────────────────────────────────────────

async def _handle_login_codex_api_key_post(request: Request) -> Response:
    """POST /login/codex/api-key — store a pasted OpenAI API key."""
    if not _backend_enabled("codex"):
        return JSONResponse({"error": _backend_not_enabled_message("codex")}, status_code=400)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Request body must be JSON."}, status_code=400)
    secret = body.get("secret") if isinstance(body, dict) else None
    if not isinstance(secret, str) or not secret.strip():
        return JSONResponse({"error": "'secret' must be a non-empty string."}, status_code=400)
    _cred_store.put("codex", "api-key", secret.strip())
    _security.audit_auth_event(
        action="login", outcome="success", account="codex",
        source=_request_source(request), emit=logger.info,
    )
    st = _cred_store.status().get("codex", {})
    return JSONResponse({
        "status": "stored",
        "backend": "codex",
        "method": "api-key",
        "stored_at": st.get("stored_at"),
    })


async def _handle_login_codex_chatgpt_post(request: Request) -> Response:
    """POST /login/codex/chatgpt — initiate Codex ChatGPT device flow.

    Starting a flow no longer returns 409 when a credential already exists.
    """
    if not _backend_enabled("codex"):
        return JSONResponse({"error": _backend_not_enabled_message("codex")}, status_code=400)
    if CODEX_FLOW.state is not None:
        return JSONResponse(
            {"error": "Codex login already in progress. Run 'ghostship auth logout codex' to cancel, or poll GET /login/codex."},
            status_code=409,
        )
    try:
        podman = _get_podman()
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)
    result = _lc()._initiate_codex_login(podman)
    if result.get("login_pending"):
        return JSONResponse(
            {"error": "Codex login already in progress. Run 'ghostship auth logout codex' to cancel, or poll GET /login/codex."},
            status_code=409,
        )
    if "error" in result:
        return JSONResponse({"error": result["error"]}, status_code=500)
    return JSONResponse({
        "status": "pending",
        "login_url": result.get("login_url"),
        "code": result.get("code"),
    })


# ── POST /logout/codex ────────────────────────────────────────────────────────

async def _handle_logout_codex_post_new(request: Request) -> Response:
    """POST /logout/codex — cancel a pending codex login and remove its credential."""
    return _logout("codex", request)
