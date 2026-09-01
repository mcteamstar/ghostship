"""Security hardening primitives for the Ghost Academy transport (TRN-70).

This module is the single home for the security guarantees the OpenSpec change
`trn-70-security-hardening` makes enforceable:

- secrets-management: one accessor all secret reads go through, plus a logging
  redaction filter so secret values never reach logs, errors, or responses.
- authentication-security: an adaptive one-way credential hasher (Argon2id with
  a stdlib scrypt fallback), a brute-force throttle, and a bounded/revocable
  session store.
- input-validation: server-side validators and context-aware output encoding.
- audit logging: a structured auth/authz audit event emitter that never carries
  a credential or token value.

The transport is a single-bearer-key gateway, so most of these are library
primitives used at the relevant entry points rather than a user-account system.
They are written to be import-safe with no third-party dependency: Argon2 is
used when the `argon2-cffi` library is present and scrypt (stdlib `hashlib`) is
the accepted fallback, matching the spec's "Argon2id or bcrypt" requirement.
"""
from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote

logger = logging.getLogger(__name__)


# ── Secrets management ────────────────────────────────────────────────────────

# Marker written in place of any redacted secret value.
REDACTION_MARKER = "***REDACTED***"


def get_secret(
    name: str,
    *,
    secret_file: str | None = None,
    env_var: str | None = None,
    default: str = "",
    logger_: logging.Logger | None = None,
) -> str:
    """Single accessor every secret read goes through (secrets-management 1.1).

    Resolution order, most-managed first:
      1. A managed secret file (e.g. a Podman/K8s secret mounted at
         ``/run/secrets/<name>``) when ``secret_file`` is given and present.
      2. An injected environment variable (dev / deprecated) when ``env_var``
         is given.
      3. ``default`` (auth-disabling empty string by convention).

    Centralising reads here is what makes redaction and rotation enforceable in
    one place rather than scattered across the codebase. The returned value is
    never logged by this function.
    """
    log = logger_ or logger
    path = secret_file if secret_file is not None else f"/run/secrets/{name}"
    try:
        from pathlib import Path

        p = Path(path)
        if p.is_file():
            value = p.read_text().strip()
            if value:
                register_secret(value)
                return value
    except Exception:
        pass

    if env_var:
        value = os.environ.get(env_var, "").strip()
        if value:
            log.warning(
                "%s loaded from environment variable %s (DEPRECATED); prefer a "
                "managed secret file at %s.",
                name,
                env_var,
                path,
            )
            register_secret(value)
            return value

    log.info("No value configured for secret %r (checked %s%s).", name, path,
             f" and ${env_var}" if env_var else "")
    return default


# Live secret values registered for redaction. Stored so the logging filter can
# scrub them out of any record regardless of where it originates.
_REGISTERED_SECRETS: set[str] = set()
_REGISTERED_LOCK = threading.Lock()


def register_secret(value: str) -> None:
    """Register a live secret value so it is redacted from logs/errors."""
    if value and len(value) >= 8:  # do not redact trivially short strings
        with _REGISTERED_LOCK:
            _REGISTERED_SECRETS.add(value)


def redact(text: str) -> str:
    """Replace any registered secret value in ``text`` with the marker."""
    if not text:
        return text
    with _REGISTERED_LOCK:
        registered = tuple(_REGISTERED_SECRETS)
    for value in registered:
        if value and value in text:
            text = text.replace(value, REDACTION_MARKER)
    return text


def _needs_redact(text: str) -> bool:
    """Fast pre-check: return True if *text* contains any registered secret."""
    with _REGISTERED_LOCK:
        return any(v and v in text for v in _REGISTERED_SECRETS)


class SecretRedactionFilter(logging.Filter):
    """Logging filter that scrubs registered secret values from every record
    (secrets-management 1.3). Attach to the root logger at startup so no log
    line, formatted message, or exception text carries a secret value.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: (redact(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(
                        redact(a) if isinstance(a, str) else a for a in record.args
                    )
            # Redact exception text — exc_info is a (type, value, traceback) tuple;
            # exc_text is the pre-formatted string (set after the first format call).
            # Both can carry a secret if an exception message contains one.
            if record.exc_info and record.exc_info[1] is not None:
                exc_val = record.exc_info[1]
                exc_str = str(exc_val)
                if exc_str and _needs_redact(exc_str):
                    # Replace the exception value with a sanitised wrapper so
                    # formatters see the redacted text instead of the raw args.
                    record.exc_text = redact(exc_str)
                    record.exc_info = None  # suppress raw traceback re-format
            if isinstance(record.exc_text, str) and _needs_redact(record.exc_text):
                record.exc_text = redact(record.exc_text)
        except Exception:
            # A redaction failure must never suppress a log record.
            pass
        return True


def install_redaction_filter(root: logging.Logger | None = None) -> SecretRedactionFilter:
    """Install the redaction filter on the root logger and its handlers."""
    target = root or logging.getLogger()
    filt = SecretRedactionFilter()
    target.addFilter(filt)
    for handler in target.handlers:
        handler.addFilter(filt)
    return filt


# ── Credential hashing (authentication-security: credential storage) ──────────

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
# n * r * p * 128 * 2 bytes ≈ 64 MiB for these params; give headroom so the
# stdlib/OpenSSL memory guard does not reject the call.
_SCRYPT_MAXMEM = 128 * 1024 * 1024


def _argon2_available() -> bool:
    try:
        import argon2  # noqa: F401

        return True
    except Exception:
        return False


def hash_password(password: str) -> str:
    """Return a salted, adaptive one-way hash storing algorithm + parameters.

    Uses Argon2id when available (OWASP first choice), else stdlib scrypt — a
    memory-hard, salted adaptive KDF and the accepted fallback. The returned
    string is self-describing (algo + params encoded) so parameters can be
    raised later without breaking verification. The cleartext is never stored.
    """
    if not isinstance(password, str) or password == "":
        raise ValueError("password must be a non-empty string")
    if _argon2_available():
        from argon2 import PasswordHasher

        return PasswordHasher().hash(password)  # encodes algo+params+salt
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
        maxmem=_SCRYPT_MAXMEM,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{salt.hex()}${dk.hex()}"
    )


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash (constant-time where possible)."""
    if not password or not stored:
        return False
    try:
        if stored.startswith("$argon2") and _argon2_available():
            from argon2 import PasswordHasher
            from argon2.exceptions import VerifyMismatchError

            try:
                PasswordHasher().verify(stored, password)
                return True
            except VerifyMismatchError:
                return False
        if stored.startswith("scrypt$"):
            _algo, n, r, p, salt_hex, dk_hex = stored.split("$")
            dk = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(dk_hex)),
                maxmem=_SCRYPT_MAXMEM,
            )
            return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False
    return False


def needs_rehash(stored: str) -> bool:
    """Whether ``stored`` uses a legacy/weaker scheme and should be upgraded on
    the next successful login (opportunistic rehash — auth hardening 2.2).
    """
    if _argon2_available():
        # Prefer Argon2id; any non-argon2 hash is a candidate to upgrade.
        return not stored.startswith("$argon2")
    # Without argon2, only truly weak (fast/unsalted) hashes need upgrading.
    return not stored.startswith("scrypt$")


# ── Brute-force throttling (authentication-security) ──────────────────────────

@dataclass
class Throttle:
    """Sliding-window failed-attempt throttle keyed on account+source.

    Rejects further attempts once ``max_failures`` is reached within
    ``window_secs``. A successful login resets the counter. State is held in
    memory here; in production the same interface is backed by the shared fast
    store (Redis) so it holds across horizontally-scaled instances.
    """

    max_failures: int = 5
    window_secs: float = 900.0  # 15 minutes
    _fails: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @staticmethod
    def _key(account: str, source: str) -> str:
        return f"{account}\x00{source}"

    def _prune(self, key: str, now: float) -> list[float]:
        stamps = [t for t in self._fails.get(key, []) if now - t < self.window_secs]
        if stamps:
            self._fails[key] = stamps
        else:
            self._fails.pop(key, None)
        return stamps

    def is_locked(self, account: str, source: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        key = self._key(account, source)
        with self._lock:
            return len(self._prune(key, now)) >= self.max_failures

    def record_failure(self, account: str, source: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        key = self._key(account, source)
        with self._lock:
            stamps = self._prune(key, now)
            stamps.append(now)
            self._fails[key] = stamps

    def record_success(self, account: str, source: str) -> None:
        """Reset the failed-attempt counter for the account+source."""
        with self._lock:
            self._fails.pop(self._key(account, source), None)


# ── HTTP request rate limiting (transport-security) ───────────────────────────

@dataclass
class RateLimiter:
    """Sliding-window request-rate limiter keyed on an arbitrary caller string.

    Allows at most ``max_requests`` recorded hits per ``window_secs`` for a
    given key. Uses the same in-memory sliding-window pruning pattern as
    ``Throttle``; state is held per-process and resets on restart. Thread-safe:
    ``record`` prunes, checks, and appends atomically under the lock so two
    concurrent callers at the boundary can never both be admitted past the
    limit.
    """

    max_requests: int
    window_secs: float
    _hits: dict[str, list[float]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, key: str, now: float) -> list[float]:
        stamps = [t for t in self._hits.get(key, []) if now - t < self.window_secs]
        if stamps:
            self._hits[key] = stamps
        else:
            self._hits.pop(key, None)
        return stamps

    def is_limited(self, key: str, now: float | None = None) -> bool:
        """Whether ``key`` is at/over its limit right now (read-only, no record)."""
        now = time.time() if now is None else now
        with self._lock:
            return len(self._prune(key, now)) >= self.max_requests

    def record(self, key: str, now: float | None = None) -> bool:
        """Atomically prune, check, and record one hit for ``key``.

        Returns ``True`` if the hit was within the limit and recorded; returns
        ``False`` without recording if ``key`` is already at ``max_requests``
        for the current window.
        """
        now = time.time() if now is None else now
        with self._lock:
            stamps = self._prune(key, now)
            if len(stamps) >= self.max_requests:
                return False
            stamps.append(now)
            self._hits[key] = stamps
            return True


# ── Bounded, revocable sessions (authentication-security) ─────────────────────

@dataclass
class SessionStore:
    """Sessions with a finite lifetime and a server-side revocation set.

    A short opaque token is issued with an expiry; ``validate`` rejects it once
    expired or once revoked. The revocation set is the authoritative override
    that lets logout/admin-revoke take effect immediately, before natural
    expiry.
    """

    lifetime_secs: float = 3600.0
    _issued: dict[str, float] = field(default_factory=dict)  # token -> expires_at
    _revoked: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def issue(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._issued[token] = now + self.lifetime_secs
        return token

    def validate(self, token: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            if token in self._revoked:
                return False
            expires = self._issued.get(token)
            if expires is None:
                return False
            if now >= expires:
                # Expired — drop it so the map stays bounded.
                self._issued.pop(token, None)
                return False
            return True

    def revoke(self, token: str) -> None:
        with self._lock:
            self._revoked.add(token)
            self._issued.pop(token, None)


# ── Input validation (input-validation) ──────────────────────────────────────

def validate_str(
    value: object,
    *,
    pattern: re.Pattern[str] | None = None,
    max_len: int = 256,
    min_len: int = 0,
    field: str = "value",
) -> str:
    """Validate an untrusted string by type, length, and format; raise on failure.

    Returns the value unchanged when valid so callers use the checked value.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not (min_len <= len(value) <= max_len):
        raise ValueError(
            f"{field} length {len(value)} out of range [{min_len}, {max_len}]"
        )
    if pattern is not None and not pattern.fullmatch(value):
        raise ValueError(f"{field} does not match the required format")
    return value


# ── Context-aware output encoding (input-validation) ──────────────────────────

def encode_html_text(value: str) -> str:
    """Encode untrusted data for an HTML text/element context."""
    return html.escape(value, quote=False)


def encode_html_attr(value: str) -> str:
    """Encode untrusted data for an HTML attribute-value context."""
    return html.escape(value, quote=True)


def encode_url_component(value: str) -> str:
    """Percent-encode untrusted data for use as a URL path/query component."""
    return quote(value, safe="")


# ── Security response headers (transport-security) ────────────────────────────

# CSP intentionally starts in report-only during staged rollout (task 3.2/3.5).
DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'; object-src 'none'"
DEFAULT_HSTS = "max-age=63072000; includeSubDomains"


def security_headers(
    *,
    https: bool,
    csp_report_only: bool = True,
    csp: str = DEFAULT_CSP,
    hsts: str = DEFAULT_HSTS,
) -> list[tuple[bytes, bytes]]:
    """Return the baseline security response headers as ASGI (bytes, bytes) pairs.

    Always emits ``X-Content-Type-Options: nosniff``, clickjacking protection
    (``X-Frame-Options`` plus CSP ``frame-ancestors``), and a Content-Security
    -Policy. HSTS is added only on HTTPS responses (a non-zero max-age).
    CSP ships report-only first and flips to enforce once violations are
    triaged.
    """
    headers: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
    ]
    csp_header = b"content-security-policy-report-only" if csp_report_only else b"content-security-policy"
    headers.append((csp_header, csp.encode("latin-1")))
    if https:
        headers.append((b"strict-transport-security", hsts.encode("latin-1")))
    return headers


# ── Audit logging (authentication-security: audit logging) ────────────────────

_audit_logger = logging.getLogger("ghostship.audit")


def audit_auth_event(
    *,
    action: str,
    outcome: str,
    account: str | None = None,
    source: str | None = None,
    emit: Callable[[str], None] | None = None,
) -> dict:
    """Record an audit event for an authentication/authorization decision.

    The event captures outcome, timestamp, account identifier, and source, and
    NEVER includes a credential or token value. Returns the event dict so the
    caller (or a test) can inspect it.
    """
    event = {
        "kind": "auth_audit",
        "action": action,
        "outcome": outcome,
        "account": account,
        "source": source,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # Redact defensively in case a caller passed a value that was registered.
    line = redact(
        f"auth_audit action={action} outcome={outcome} "
        f"account={account or '-'} source={source or '-'} ts={event['ts']}"
    )
    (emit or _audit_logger.info)(line)
    return event
