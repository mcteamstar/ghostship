#!/usr/bin/env python3
"""Sign and write the crew's security + admission policy files.

Runs inside a crew container via
``python3 /scripts/inject_policy.py <crew_dir> <b64_payload>``, where
``b64_payload`` is a base64-encoded JSON object with keys ``policy`` (the
policy document, including its ``identity`` block but without a signature)
and ``policy_signing_key`` (the dedicated HMAC key used to sign the policy —
distinct from ``admiral_secret``, which is kept separate and never written
to ``admission_policy.json``).

Signing runs inside the container so the canonicalization is always the
same version as the verifier. The KiroCrew canonicalization is inlined
here rather than importing ``kiro_crew`` — this avoids import
side-effects during setup and keeps signing independent of the internal
module path.

The payload is base64-encoded via argv because the transport's exec API is
stdout-only (no stdin) and to avoid interpolating the secret as a literal.

Args (argv):
    1. crew_dir     — the ``.kiro/crew`` directory to write policy files into
    2. b64_payload  — base64-encoded JSON {"policy": {...}, "policy_signing_key": "..."}

Both files are written with mode 0600. Prints
``policy injected version=<v>``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import pathlib
import sys


def sign_policy(policy: dict, secret: str) -> dict:
    """Return ``policy`` with ``identity.signature`` set via HMAC-SHA256.

    The signing payload is the whole document minus ``identity.signature``.
    ``identity.issuer`` IS covered so an attacker cannot re-label a signed
    policy.
    """
    body = {k: v for k, v in policy.items() if k != "identity"}
    identity = policy.get("identity", {})
    rest = {k: v for k, v in identity.items() if k != "signature"}
    if rest:
        body["identity"] = rest
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    signed = {**policy}
    signed["identity"] = {**signed.get("identity", {}), "signature": sig}
    return signed


def _write_0600(path: pathlib.Path, content: str) -> None:
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)


def inject_policy(crew_dir: str, policy: dict, policy_signing_key: str) -> str:
    """Sign the policy, write both files, return the policy version string."""
    policy_version = policy.get("version", "1")
    signed = sign_policy(policy, policy_signing_key)
    policy_body = json.dumps(signed, indent=2)
    # admission_policy.json stores the verification flag and trust key.
    # trust_keys is required by KiroCrew's governance API to verify the
    # security policy signature — without it the gateway rejects the policy.
    # The policy_signing_key stored here is a dedicated signing key, distinct
    # from admiral_secret, so agent-readable admission_policy.json no longer
    # exposes the Admiral mail-signing secret.
    admission_body = json.dumps(
        {
            "require_policy_signature": True,
            "trust_keys": {"ghostship": policy_signing_key},
        },
        indent=2,
    )
    d = pathlib.Path(crew_dir)
    d.mkdir(parents=True, exist_ok=True)
    _write_0600(d / "security_policy.json", policy_body)
    _write_0600(d / "admission_policy.json", admission_body)
    return policy_version


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: inject_policy.py <crew_dir> <b64_payload>", file=sys.stderr)
        return 2
    data = json.loads(base64.b64decode(argv[2]).decode())
    version = inject_policy(argv[1], data["policy"], data["policy_signing_key"])
    print(f"policy injected version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
