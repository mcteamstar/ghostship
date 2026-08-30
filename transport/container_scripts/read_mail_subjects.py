#!/usr/bin/env python3
"""Read Subject lines from mailboxes in one exec.

Runs inside a crew container via
``python3 /scripts/read_mail_subjects.py <mailboxes_json>``.

This replaces the former base64-encode-and-exec workaround: file-based
invocation removes the shell-quoting hazard that motivated it.

Args (argv):
    1. mailboxes_json — JSON list of mailbox names (under /var/mail/<name>)

Supports Maildir (``new/`` + ``cur/``) and legacy mbox (a single file).
Reading never modifies the files. Prints a JSON object mapping mailbox
name -> list of Subject header values (empty list for an empty mailbox).
"""
from __future__ import annotations

import json
import os
import re
import sys


def read_mailbox(path: str) -> str:
    """Return the concatenated raw text of all messages in ``path``.

    Supports Maildir (a directory with ``new/`` and ``cur/``) and legacy
    mbox (a single file).
    """
    if os.path.isdir(os.path.join(path, "new")):
        parts = []
        for subdir in ("new", "cur"):
            d = os.path.join(path, subdir)
            if not os.path.isdir(d):
                continue
            for fname in os.listdir(d):
                try:
                    with open(os.path.join(d, fname)) as fh:
                        parts.append(fh.read())
                except OSError:
                    pass
        return "".join(parts)
    if os.path.isfile(path):
        try:
            with open(path) as fh:
                return fh.read()
        except OSError:
            return ""
    return ""


def read_subjects(
    mailboxes: list[str], root: str = "/var/mail"
) -> dict[str, list[str]]:
    """Return {name: [subject, ...]} for each mailbox."""
    subjects: dict[str, list[str]] = {}
    for name in mailboxes:
        raw = read_mailbox(os.path.join(root, name))
        subjects[name] = re.findall(r"(?m)^Subject: (.+)$", raw)
    return subjects


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: read_mail_subjects.py <mailboxes_json>", file=sys.stderr)
        return 2
    mailboxes = json.loads(argv[1])
    print(json.dumps(read_subjects(mailboxes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
