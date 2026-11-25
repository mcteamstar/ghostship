#!/usr/bin/env python3
"""Read mailbox subject lines for Radar, strictly, in one exec.

Runs inside a running crew container via
``python3 /scripts/read_crew_mail_subjects.py <mailboxes_json>``.

Unlike ``read_mail_subjects.py`` (captain status counts), this reader is
strict: a mailbox path that does not exist is an empty mailbox, but any other
read error exits non-zero so the caller reports the crew as unavailable rather
than showing a partial or false-empty result.

Args (argv):
    1. mailboxes_json -- JSON list of mailbox names (under /var/mail/<name>)

Output: a JSON object mapping mailbox name to a list of subject strings,
newest first, capped at ``SUBJECT_LIMIT`` entries of at most
``SUBJECT_MAX_CHARS`` characters. Mailboxes that hold no message with a
Subject header map to an empty list. Reading never modifies any file.

Maildir ordering: ``maildeliver`` names files ``<epoch>.<pid>.<rand>.<host>``,
so the numeric prefix gives delivery order. Legacy mbox files are append
ordered, so their messages are read in reverse file order.
"""
from __future__ import annotations

import email.parser
import json
import os
import re
import sys

MAIL_ROOT = "/var/mail"
SUBJECT_LIMIT = 50
SUBJECT_MAX_CHARS = 200
HEADER_READ_LIMIT = 64 * 1024


def _clean_subject(raw: str) -> str:
    """Collapse folded whitespace and truncate to the Radar subject limit."""
    return " ".join(raw.split())[:SUBJECT_MAX_CHARS]


def _subject_from_text(text: str) -> str:
    msg = email.parser.HeaderParser().parsestr(text)
    return _clean_subject(msg.get("Subject", "") or "")


def _maildir_sort_key(filename: str) -> tuple[int, str]:
    prefix = filename.split(".", 1)[0]
    return (int(prefix) if prefix.isdigit() else 0, filename)


def _maildir_subjects(path: str) -> list[str]:
    files: list[tuple[tuple[int, str], str]] = []
    for subdir in ("new", "cur"):
        directory = os.path.join(path, subdir)
        if not os.path.isdir(directory):
            continue
        for fname in os.listdir(directory):
            files.append((_maildir_sort_key(fname), os.path.join(directory, fname)))
    files.sort(key=lambda item: item[0], reverse=True)

    subjects: list[str] = []
    for _, fpath in files:
        if len(subjects) >= SUBJECT_LIMIT:
            break
        with open(fpath, "rb") as fh:
            head = fh.read(HEADER_READ_LIMIT).decode("utf-8", errors="replace")
        subject = _subject_from_text(head)
        if subject:
            subjects.append(subject)
    return subjects


def _mbox_subjects(path: str) -> list[str]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    chunks = [chunk for chunk in re.split(r"(?m)^From ", raw) if chunk.strip()]

    subjects: list[str] = []
    for chunk in reversed(chunks):
        if len(subjects) >= SUBJECT_LIMIT:
            break
        subject = _subject_from_text(_strip_mbox_envelope(chunk))
        if subject:
            subjects.append(subject)
    return subjects


_HEADER_FIELD_RE = re.compile(r"^[!-9;-~]+:")


def _strip_mbox_envelope(chunk: str) -> str:
    """Drop the ``sender date`` remainder of an mbox envelope line.

    The splitter removes the leading ``From `` but leaves the remainder on the
    first line. A real header field name has no spaces before its colon, so
    the envelope is dropped unless the first line is already a header field.
    """
    first, _, rest = chunk.partition("\n")
    return chunk if _HEADER_FIELD_RE.match(first) else rest


def read_mailbox_subjects(name: str, root: str = MAIL_ROOT) -> list[str]:
    """Return up to SUBJECT_LIMIT subjects for one mailbox, newest first.

    Raises OSError for any read failure on a mailbox that exists.
    """
    path = os.path.join(root, name)
    if os.path.isdir(os.path.join(path, "new")) or os.path.isdir(os.path.join(path, "cur")):
        return _maildir_subjects(path)
    if os.path.isfile(path):
        return _mbox_subjects(path)
    return []


def read_subjects(names: list[str], root: str = MAIL_ROOT) -> dict[str, list[str]]:
    return {name: read_mailbox_subjects(name, root) for name in names}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: read_crew_mail_subjects.py <mailboxes_json>", file=sys.stderr)
        return 2
    names = json.loads(argv[1])
    try:
        result = read_subjects(names)
    except OSError as exc:
        print(f"mail subject read failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
