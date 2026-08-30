#!/usr/bin/env python3
"""Count messages across mailboxes in one exec.

Runs inside a crew container via
``python3 /scripts/read_mail_counts.py <mailboxes_json>``.

Args (argv):
    1. mailboxes_json — JSON list of mailbox names (under /var/mail/<name>)

Supports Maildir (``new/`` + ``cur/``) and legacy mbox (a single file with
``From `` separators) for backward compatibility. Prints a JSON object
mapping mailbox name -> count, omitting mailboxes with a zero count.
"""
from __future__ import annotations

import json
import os
import re
import sys


def count_mailbox(path: str) -> int:
    """Count messages in a Maildir dir or legacy mbox file at ``path``."""
    if os.path.isdir(os.path.join(path, "new")):
        total = 0
        for subdir in ("new", "cur"):
            d = os.path.join(path, subdir)
            if os.path.isdir(d):
                total += len(os.listdir(d))
        return total
    if os.path.isfile(path):
        with open(path) as fh:
            return len(re.findall(r"(?m)^From [^\n]*$", fh.read()))
    return 0


def read_counts(mailboxes: list[str], root: str = "/var/mail") -> dict[str, int]:
    """Return {name: count} for each mailbox, omitting zero counts."""
    counts: dict[str, int] = {}
    for name in mailboxes:
        n = count_mailbox(os.path.join(root, name))
        if n:
            counts[name] = n
    return counts


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: read_mail_counts.py <mailboxes_json>", file=sys.stderr)
        return 2
    mailboxes = json.loads(argv[1])
    print(json.dumps(read_counts(mailboxes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
