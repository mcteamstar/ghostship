"""Guardrail test — TRN-221: SEL key moved to ``$KIROCREW_HOME/trust/``.

KiroCrew 0.9.0 relocated the Security Event Log (SEL) signing key into a
consolidated ``$KIROCREW_HOME/trust/`` root. The SEL key is a gateway-internal
credential; no ghostship transport code reads it today. This static-assertion
test scans every Python file under ``transport/`` and fails if a pre-0.9.0 SEL
key path literal is ever reintroduced, so a future PR cannot silently regress
to a hardcoded SEL path.

It deliberately does NOT flag the known-unrelated strings:

- the SQL ``SELECT`` keyword in ``transport/container_scripts/read_auth.py``
  (and the inlined extract in ``transport/lifecycle.py``),
- the ``.local_secret`` docstring in ``transport/lifecycle.py`` (internal-API
  secret, not the SEL key),
- ``policy_signing_key`` / ``trust_keys`` in
  ``transport/container_scripts/inject_policy.py`` (ghostship's own policy HMAC
  key, not the SEL key).

See ``openspec/changes/trn-221-kc090-sel-key-trust-dir/`` (design.md §3,
specs/transport-test-coverage/spec.md).
"""
from __future__ import annotations

import pathlib
import re

# Pre-0.9.0 SEL path literals that must NOT reappear in ghostship transport
# code. The pattern targets ``sel_key`` / ``sel-key`` / ``sel.key`` / ``selkey``
# and a ``/sel/`` path segment. It is case-insensitive, but anchored so the SQL
# ``SELECT`` keyword, ``session_key``, ``_RAVEN_SELF_CANCEL`` ("SELF"), the
# ``.local_secret`` docstring and ``policy_signing_key`` do not match.
_FORBIDDEN = re.compile(
    r"""(?xi)
        (?:['"][^'"]*/)?            # optional path prefix in a string literal
        sel[_.-]?key                # sel_key / sel-key / sel.key / selkey
      | /sel/                       # a /sel/ path segment
    """
)

# tests/unit/<this file> -> repo root is parents[2]; transport/ lives there.
_TRANSPORT = pathlib.Path(__file__).resolve().parents[2] / "transport"


def test_no_hardcoded_sel_key_path():
    assert _TRANSPORT.is_dir(), f"transport/ not found at {_TRANSPORT}"
    offenders = []
    for py in sorted(_TRANSPORT.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN.search(line):
                offenders.append(f"{py}:{i}: {line.strip()}")
    assert not offenders, (
        "SEL key must be read from $KIROCREW_HOME/trust/ (KiroCrew 0.9.0+); "
        "no hardcoded pre-0.9.0 SEL path is allowed:\n" + "\n".join(offenders)
    )
