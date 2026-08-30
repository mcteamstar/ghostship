#!/usr/bin/env python3
"""Deliver a captain mail message via the container's MTA.

Runs inside a crew container via
``python3 /scripts/append_captain_mail.py <b64_message>``, piping the
decoded RFC822 message through ``/usr/local/bin/maildeliver
captain@localhost`` for atomic Maildir delivery.

Passing the message base64-encoded via argv (rather than interpolating it
into an inline ``-c`` string) removes the shell-quoting hazard the inline
version worked around, and the transport's exec API is stdout-only (no
stdin), so argv is the delivery channel.

Args (argv):
    1. b64_message — base64-encoded raw RFC822 message bytes

Prints ``captain mail delivered via MTA`` on success; exits non-zero on
maildeliver failure.
"""
from __future__ import annotations

import base64
import subprocess
import sys


def deliver(msg: bytes) -> None:
    """Pipe ``msg`` through maildeliver to the captain mailbox."""
    proc = subprocess.run(
        ["/usr/local/bin/maildeliver", "captain@localhost"],
        input=msg,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"maildeliver failed: {proc.stderr.decode()}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: append_captain_mail.py <b64_message>", file=sys.stderr)
        return 2
    deliver(base64.b64decode(argv[1]))
    print("captain mail delivered via MTA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
