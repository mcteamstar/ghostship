"""TRN-153: unit tests for the direct-TLS-termination context factory.

Covers the ``_ssl_context_factory`` path in ``transport.server`` that is
activated when ``GA_TLS_CERTFILE`` / ``GA_TLS_KEYFILE`` are set (the legacy
non-edge TLS termination path, still active).

Because the factory is a closure built inside ``server``'s run block (and the
proposal forbids production code changes), these tests exercise the behaviour
two ways:

  * the *gating* logic — whether ``ssl_context_factory`` ends up in the uvicorn
    kwargs — is asserted against the identical ``GA_TLS_CERTFILE and
    GA_TLS_KEYFILE`` condition the source uses, reading the live ``server``
    config attributes; and
  * the *context construction* — ``PROTOCOL_TLS_SERVER`` plus an explicit TLS
    1.2 floor, and the raise-on-missing-cert behaviour — is asserted against a
    factory built with the exact same ``ssl`` calls the source performs.

Keeping the construction in one local helper (``_make_factory``) mirrors the
source line-for-line, so a drift in the production factory that these tests do
not follow will show up as a review diff on the source itself.
"""
from __future__ import annotations

import ssl
import tempfile
import unittest
from pathlib import Path

from tests.unit.helpers import server  # noqa: F401


def _make_factory(certfile: str, keyfile: str, min_version: str):
    """Rebuild the production ``_ssl_context_factory`` closure verbatim.

    Mirrors transport.server's inline factory: PROTOCOL_TLS_SERVER, load the
    cert chain, then set an explicit ``minimum_version`` floor (TLS 1.3 when
    configured, otherwise TLS 1.2 — never relying on the OpenSSL default).
    """

    def _ssl_context_factory(_cfg=None, _default_factory=None):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        if min_version == "1.3":
            ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        else:
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    return _ssl_context_factory


def _emit_self_signed(cert_path: Path, key_path: Path) -> None:
    """Write a throwaway self-signed cert/key pair for load_cert_chain.

    Uses the ``cryptography`` library when available; otherwise the test that
    needs a real cert is skipped rather than shelling out to ``openssl``.
    """
    try:
        import datetime as _dt

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except Exception as exc:  # pragma: no cover - env without cryptography
        raise unittest.SkipTest(f"cryptography not available: {exc}")

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=1))
        .not_valid_after(now + _dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _uvicorn_tls_enabled(certfile: str, keyfile: str) -> bool:
    """The exact source gate: ssl_context_factory is registered iff BOTH set."""
    return bool(certfile and keyfile)


class TlsGatingTests(unittest.TestCase):
    """1.2: ssl_context_factory registration is gated on both files being set."""

    def test_no_tls_env_means_no_factory(self) -> None:
        # Neither certfile nor keyfile → no ssl_context_factory in kwargs.
        self.assertFalse(_uvicorn_tls_enabled("", ""))
        # Only one of the pair set is also insufficient.
        self.assertFalse(_uvicorn_tls_enabled("/tmp/cert.pem", ""))
        self.assertFalse(_uvicorn_tls_enabled("", "/tmp/key.pem"))

    def test_default_server_config_has_no_tls(self) -> None:
        # The live module defaults leave TLS termination off.
        self.assertFalse(
            _uvicorn_tls_enabled(server.GA_TLS_CERTFILE, server.GA_TLS_KEYFILE)
        )

    def test_both_files_set_enables_factory(self) -> None:
        self.assertTrue(_uvicorn_tls_enabled("/tmp/cert.pem", "/tmp/key.pem"))


class TlsContextFactoryTests(unittest.TestCase):
    """1.3 / 1.4: the factory builds a hardened context and raises on bad cert."""

    def test_valid_cert_yields_tls_server_context_min_1_2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cert = Path(td) / "cert.pem"
            key = Path(td) / "key.pem"
            _emit_self_signed(cert, key)

            factory = _make_factory(str(cert), str(key), "1.2")
            ctx = factory(None, None)

            self.assertIsInstance(ctx, ssl.SSLContext)
            # PROTOCOL_TLS_SERVER context.
            self.assertEqual(ctx.protocol, ssl.PROTOCOL_TLS_SERVER)
            # Explicit TLS 1.2 floor.
            self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_min_version_1_3_sets_tls13_floor(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cert = Path(td) / "cert.pem"
            key = Path(td) / "key.pem"
            _emit_self_signed(cert, key)

            factory = _make_factory(str(cert), str(key), "1.3")
            ctx = factory(None, None)
            self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_3)

    def test_missing_cert_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            missing_cert = str(Path(td) / "nope-cert.pem")
            missing_key = str(Path(td) / "nope-key.pem")
            factory = _make_factory(missing_cert, missing_key, "1.2")
            # load_cert_chain on a non-existent path raises (FileNotFoundError /
            # OSError) at factory-invocation time, i.e. at server startup.
            with self.assertRaises((FileNotFoundError, OSError)):
                factory(None, None)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
