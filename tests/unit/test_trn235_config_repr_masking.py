"""Unit tests for Config.__repr__ secret masking (trn-235-shell-exec-hardening, SEC-3).

The Config dataclass holds live credential values. A ``__repr__`` override must
replace non-empty values of the sensitive fields with ``"***"`` so that any log
call including ``repr(cfg)`` / ``str(cfg)`` never emits a live credential.
Non-secret fields and empty secret fields must still render their real value.
"""
from __future__ import annotations

import dataclasses
import unittest

from transport.config import Config  # noqa: E402

_SECRET_FIELDS = (
    "kiro_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "claude_code_oauth_token",
)


class TestConfigReprMasking(unittest.TestCase):
    def test_nonempty_secrets_masked(self) -> None:
        cfg = Config(
            kiro_api_key="kiro-SECRET-1",
            anthropic_api_key="anthropic-SECRET-2",
            openai_api_key="openai-SECRET-3",
            claude_code_oauth_token="oauth-SECRET-4",
        )
        r = repr(cfg)
        for value in (
            "kiro-SECRET-1",
            "anthropic-SECRET-2",
            "openai-SECRET-3",
            "oauth-SECRET-4",
        ):
            self.assertNotIn(value, r)
        self.assertIn("***", r)
        # Each masked field appears as ***.
        for field in _SECRET_FIELDS:
            self.assertIn(f"{field}='***'", r)

    def test_empty_secret_fields_not_masked(self) -> None:
        # Defaults are "" — empty values stay empty, not masked.
        r = repr(Config())
        for field in _SECRET_FIELDS:
            self.assertIn(f"{field}=''", r)
        self.assertNotIn("***", r)

    def test_nonsecret_fields_rendered(self) -> None:
        cfg = Config(host="127.0.0.1", port=12345, kiro_api_key="x")
        r = repr(cfg)
        self.assertIn("host='127.0.0.1'", r)
        self.assertIn("port=12345", r)
        # The secret is masked even when non-secret fields render verbatim.
        self.assertNotIn("kiro_api_key='x'", r)
        self.assertIn("kiro_api_key='***'", r)

    def test_str_also_masks(self) -> None:
        # str() falls back to __repr__ for dataclasses, so it must mask too.
        cfg = Config(anthropic_api_key="live-token")
        self.assertNotIn("live-token", str(cfg))

    def test_repr_marker_not_a_dataclass_field(self) -> None:
        # The _SECRET_FIELDS marker must not have leaked into the dataclass fields.
        names = {f.name for f in dataclasses.fields(Config())}
        self.assertNotIn("_SECRET_FIELDS", names)


if __name__ == "__main__":
    unittest.main()
