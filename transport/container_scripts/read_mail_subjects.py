#!/usr/bin/env python3
"""Read Subject and Date lines from mailboxes in one exec.

Runs inside a crew container via
``python3 /scripts/read_mail_subjects.py <mailboxes_json>``.

This replaces the former base64-encode-and-exec workaround: file-based
invocation removes the shell-quoting hazard that motivated it.

Args (argv):
    1. mailboxes_json — JSON list of mailbox names (under /var/mail/<name>)

Supports Maildir (``new/`` + ``cur/``) and legacy mbox (a single file).
Reading never modifies the files. Prints a JSON object mapping mailbox
name -> list of ``{"subject": str, "received_at": str | null}`` dicts
(empty list for an empty mailbox).
"""
from __future__ import annotations

import email.parser
import email.utils
import json
import os
import re
import sys
from datetime import timezone


def read_mailbox(path: str) -> list[str]:
    """Return individual raw message texts from ``path``.

    Supports Maildir (a directory with ``new/`` and ``cur/``) and legacy
    mbox (a single file).  Maildir returns one entry per file; mbox splits
    on ``^From `` envelope separators.
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
        return parts
    if os.path.isfile(path):
        try:
            with open(path) as fh:
                raw = fh.read()
            # Split mbox on "From " envelope lines
            messages = re.split(r"(?m)^From ", raw)
            return [m for m in messages if m.strip()]
        except OSError:
            return []
    return []


def _parse_received_at(date_header: str) -> str | None:
    """Parse an RFC 5322 Date header into an ISO 8601 UTC string, or None."""
    if not date_header:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(date_header)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def read_subjects(
    mailboxes: list[str], root: str = "/var/mail"
) -> dict[str, list[dict]]:
    """Return {name: [{"subject": str, "received_at": str|None}, ...]} for each mailbox."""
    parser = email.parser.HeaderParser()
    result: dict[str, list[dict]] = {}
    for name in mailboxes:
        messages = read_mailbox(os.path.join(root, name))
        entries: list[dict] = []
        for raw in messages:
            # For mbox messages the first line is the envelope "From <sender> <date>"
            # line (already stripped of its leading "From " by the splitter).
            # Skip it so the parser sees RFC 5322 headers starting on line 2.
            lines = raw.split("\n", 1)
            if len(lines) == 2 and not lines[0].startswith((" ", "\t")):
                # Heuristic: if the first line contains no colon it's an mbox
                # envelope line, not a header field.
                if ":" not in lines[0]:
                    raw = lines[1]
            msg = parser.parsestr(raw)
            subject = msg.get("Subject", "").strip()
            if not subject:
                continue
            received_at = _parse_received_at(msg.get("Date", ""))
            entries.append({"subject": subject, "received_at": received_at})
        result[name] = entries
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: read_mail_subjects.py <mailboxes_json>", file=sys.stderr)
        return 2
    mailboxes = json.loads(argv[1])
    print(json.dumps(read_subjects(mailboxes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
