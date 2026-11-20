#!/usr/bin/env python3
"""Exercise verify-admiral-sig in the built crew image using Podman secrets."""

from __future__ import annotations

import argparse
import base64
import subprocess
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PUBLIC_KEY_PATH = "/run/secrets/.admiral_public_key"
SENDER = "Admiral <admiral@localhost>"
BODY = b"generated signature fixture\n"


def signed_payload(subject: str, sender: str, body: bytes) -> bytes:
    subject_bytes = subject.encode("utf-8")
    sender_bytes = sender.encode("utf-8")
    return (
        f"{len(subject_bytes)}\n".encode("ascii")
        + subject_bytes
        + f"{len(sender_bytes)}\n".encode("ascii")
        + sender_bytes
        + body
    )


def signed_message(subject: str, signature: str) -> bytes:
    return (
        f"From: {SENDER}\n"
        f"Subject: {subject}\n"
        f"X-Admiral-Sig: {signature}\n"
        "\n"
    ).encode("utf-8") + BODY


def run_verifier(podman: list[str], image: str, message: bytes, secret: str | None):
    command = podman + ["run", "--rm", "-i", "--network", "none"]
    if secret:
        command += ["--secret", f"{secret},target={PUBLIC_KEY_PATH}"]
    command += [
        "--entrypoint",
        "/usr/local/bin/verify-admiral-sig",
        image,
    ]
    return subprocess.run(command, input=message, capture_output=True, check=False)


def expect_exit(result, expected: int, label: str) -> None:
    if result.returncode != expected:
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        raise SystemExit(
            f"{label}: expected exit {expected}, got {result.returncode}\n"
            f"stdout: {stdout}\nstderr: {stderr}"
        )
    print(f"{label}: exit {expected}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection", default="ghost-academy")
    parser.add_argument("--image", default="localhost/spec-ops:latest")
    args = parser.parse_args()

    podman = ["podman", "--connection", args.connection]
    subprocess.run(
        podman + ["image", "inspect", args.image],
        check=True,
        capture_output=True,
    )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    subject = "generated signature fixture"
    signature = base64.urlsafe_b64encode(
        private_key.sign(signed_payload(subject, SENDER, BODY))
    ).decode("ascii").rstrip("=")
    valid = signed_message(subject, signature)
    tampered = signed_message("tampered signature fixture", signature)
    malformed_signature = base64.urlsafe_b64encode(b"malformed").decode("ascii").rstrip("=")
    malformed = signed_message(subject, malformed_signature)
    secret = f"admiral-signature-test-{uuid.uuid4().hex}"

    subprocess.run(
        podman + ["secret", "create", secret, "-"],
        input=public_key,
        check=True,
        capture_output=True,
    )
    try:
        expect_exit(run_verifier(podman, args.image, valid, secret), 0, "valid signature")
        expect_exit(run_verifier(podman, args.image, tampered, secret), 1, "tampered message")
        expect_exit(run_verifier(podman, args.image, malformed, secret), 1, "malformed signature")
        expect_exit(run_verifier(podman, args.image, valid, None), 2, "missing public key")
    finally:
        subprocess.run(
            podman + ["secret", "rm", secret],
            check=False,
            capture_output=True,
        )


if __name__ == "__main__":
    main()
