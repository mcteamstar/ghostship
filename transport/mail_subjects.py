"""Radar mailbox-subject reader (TRN-370).

Returns subject strings only, grouped by the eight established crew mailboxes.
Reading never modifies a mailbox.

Two read paths:

- Running crews: one container exec of ``read_crew_mail_subjects.py``.
- Stopped crews: Podman archive API reads of ``/var/mail/<name>``. The
  container is confirmed to exist first, so the archive API's 404 can be read
  as "path absent" rather than "container absent".

Strictness contract: a missing mailbox path is an empty mailbox. Any other
failure raises ``MailSubjectsUnavailable`` so the caller reports the whole
crew as unavailable instead of a partial or false-empty result.
"""

from __future__ import annotations

import email.parser
import io
import json
import logging
import posixpath
import re
import tarfile
from typing import Any

try:
    from podman import ArchivePathNotFound  # container: flat /app/
except ModuleNotFoundError:
    from transport.podman import ArchivePathNotFound  # local dev

try:
    from constants import SCRIPTS_DIR  # container: flat /app/
except ModuleNotFoundError:
    from transport.constants import SCRIPTS_DIR  # local dev

logger = logging.getLogger(__name__)

MAIL_ROOT = "/var/mail"
MAILBOXES = (
    "ghost", "spectre", "banshee", "wraith", "reaper", "raven", "captain", "admiral",
)
SUBJECT_LIMIT = 50
SUBJECT_MAX_CHARS = 200
_HEADER_READ_LIMIT = 64 * 1024
_RUNNING_SCRIPT = f"{SCRIPTS_DIR}/read_crew_mail_subjects.py"


class MailSubjectsUnavailable(RuntimeError):
    """The mailbox source could not be read completely."""


def _clean_subject(raw: str) -> str:
    return " ".join(raw.split())[:SUBJECT_MAX_CHARS]


def _finalize(subjects: list[str]) -> list[str]:
    """Drop empty subjects, normalise, and apply the per-mailbox cap."""
    cleaned = [_clean_subject(s) for s in subjects]
    return [s for s in cleaned if s][:SUBJECT_LIMIT]


def _subject_from_text(text: str) -> str:
    msg = email.parser.HeaderParser().parsestr(text)
    return _clean_subject(msg.get("Subject", "") or "")


def _maildir_sort_key(filename: str) -> tuple[int, str]:
    """Order Maildir files by the epoch prefix ``maildeliver`` writes."""
    prefix = filename.split(".", 1)[0]
    return (int(prefix) if prefix.isdigit() else 0, filename)


# ── running crews: container exec ────────────────────────────────────────────

def read_running_crew(podman: Any, container: str) -> dict[str, list[str]]:
    """Read every mailbox through one exec inside a running crew."""
    try:
        raw = podman.container_exec_checked(
            container,
            ["python3", _RUNNING_SCRIPT, json.dumps(list(MAILBOXES))],
        )
    except Exception as exc:
        raise MailSubjectsUnavailable(f"mailbox exec failed: {exc}") from exc
    return _parse_exec_output(raw)


def _parse_exec_output(raw: str) -> dict[str, list[str]]:
    try:
        data = json.loads(raw.strip())
    except ValueError as exc:
        raise MailSubjectsUnavailable("mailbox exec output is not JSON") from exc
    if not isinstance(data, dict) or set(data) != set(MAILBOXES):
        raise MailSubjectsUnavailable("mailbox exec output has unexpected mailboxes")

    result: dict[str, list[str]] = {}
    for name in MAILBOXES:
        items = data[name]
        if not isinstance(items, list) or not all(isinstance(s, str) for s in items):
            raise MailSubjectsUnavailable(f"mailbox '{name}' has malformed subjects")
        result[name] = _finalize(items)
    return result


# ── stopped crews: Podman archive API ────────────────────────────────────────

def read_stopped_crew(podman: Any, container: str) -> dict[str, list[str]]:
    """Read every mailbox from a stopped crew's filesystem without starting it."""
    try:
        exists = podman.container_exists(container)
    except Exception as exc:
        raise MailSubjectsUnavailable(f"container lookup failed: {exc}") from exc
    if not exists:
        raise MailSubjectsUnavailable("crew container not found")

    result = {
        name: _read_archive_mailbox(podman, container, name) for name in MAILBOXES
    }

    # The archive API also answers 404 for a container removed mid-read, which
    # would look like eight absent mailboxes. Re-check before trusting the result.
    try:
        still_exists = podman.container_exists(container)
    except Exception as exc:
        raise MailSubjectsUnavailable(f"container lookup failed: {exc}") from exc
    if not still_exists:
        raise MailSubjectsUnavailable("crew container removed during read")
    return result


def _read_archive_mailbox(podman: Any, container: str, name: str) -> list[str]:
    path = f"{MAIL_ROOT}/{name}"
    try:
        response = podman.container_archive_get(container, path)
    except ArchivePathNotFound:
        return []
    except Exception as exc:
        raise MailSubjectsUnavailable(f"archive read failed for '{name}': {exc}") from exc

    try:
        tar_bytes = b"".join(response.iter_bytes())
    except Exception as exc:
        raise MailSubjectsUnavailable(f"archive stream failed for '{name}': {exc}") from exc
    finally:
        response.close()

    try:
        return _finalize(subjects_from_archive(tar_bytes))
    except Exception as exc:
        raise MailSubjectsUnavailable(f"mailbox '{name}' unreadable: {exc}") from exc


def _mailbox_parts(member_name: str) -> list[str]:
    return posixpath.normpath(member_name).split("/")


def _is_maildir_layout_member(member_name: str) -> bool:
    """True for a member (file or directory) under ``<mailbox>/{new,cur,tmp}``."""
    parts = _mailbox_parts(member_name)
    return len(parts) >= 2 and parts[1] in ("new", "cur", "tmp")


def _is_maildir_message(member_name: str) -> bool:
    """True for a delivered message: ``<mailbox>/{new,cur}/<file>`` exactly.

    Matches the running-crew script, which reads only the top-level ``new`` and
    ``cur`` directories. ``tmp`` files (in-flight or stale deliveries) and
    Maildir++ subfolders are not delivered mail and are ignored.
    """
    parts = _mailbox_parts(member_name)
    return len(parts) == 3 and parts[1] in ("new", "cur")


def subjects_from_archive(tar_bytes: bytes) -> list[str]:
    """Return subjects, newest first, from a tar of one mailbox.

    Maildir archives carry ``new/``, ``cur/`` or ``tmp/`` members; delivered
    messages are read in filename timestamp order. A legacy mbox archive is a
    single regular file, read in reverse file order. An archive with no regular
    files is an empty mailbox. Raises MailSubjectsUnavailable for any other
    layout or a corrupt archive.
    """
    try:
        tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*")
    except (tarfile.TarError, OSError) as exc:
        raise MailSubjectsUnavailable("archive is not a readable tar") from exc

    with tf:
        try:
            members = tf.getmembers()
        except (tarfile.TarError, OSError) as exc:
            raise MailSubjectsUnavailable("archive members are unreadable") from exc

        if any(_is_maildir_layout_member(m.name) for m in members):
            messages = [m for m in members if m.isreg() and _is_maildir_message(m.name)]
            return _maildir_subjects(tf, messages)

        regular = [m for m in members if m.isreg()]
        if not regular:
            return []
        if len(regular) > 1:
            raise MailSubjectsUnavailable("unexpected mailbox layout")
        return _mbox_subjects(tf, regular[0])


def _maildir_subjects(tf: tarfile.TarFile, members: list[tarfile.TarInfo]) -> list[str]:
    ordered = sorted(
        members,
        key=lambda m: _maildir_sort_key(posixpath.basename(m.name)),
        reverse=True,
    )
    subjects: list[str] = []
    for member in ordered:
        if len(subjects) >= SUBJECT_LIMIT:
            break
        fobj = _extract(tf, member)
        head = fobj.read(_HEADER_READ_LIMIT).decode("utf-8", errors="replace")
        subject = _subject_from_text(head)
        if subject:
            subjects.append(subject)
    return subjects


def _mbox_subjects(tf: tarfile.TarFile, member: tarfile.TarInfo) -> list[str]:
    raw = _extract(tf, member).read().decode("utf-8", errors="replace")
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


def _extract(tf: tarfile.TarFile, member: tarfile.TarInfo):
    try:
        fobj = tf.extractfile(member)
    except (tarfile.TarError, OSError) as exc:
        raise MailSubjectsUnavailable(f"cannot read member '{member.name}'") from exc
    if fobj is None:
        raise MailSubjectsUnavailable(f"cannot read member '{member.name}'")
    return fobj


# ── entry point ──────────────────────────────────────────────────────────────

def read_crew_mail_subjects(podman: Any, container: str, *, running: bool) -> dict[str, list[str]]:
    """Return ``{mailbox: [subject, ...]}`` for all eight crew mailboxes.

    Raises MailSubjectsUnavailable when any part of the read cannot complete.
    """
    if running:
        return read_running_crew(podman, container)
    return read_stopped_crew(podman, container)


def _history_header(stream) -> dict[str, str | None]:
    """Project only display metadata from a bounded header prefix."""
    from email.utils import parseaddr, parsedate_to_datetime

    message = email.parser.BytesHeaderParser().parsebytes(stream.read(_HEADER_READ_LIMIT))
    sender = parseaddr(str(message.get("From", "")))[1]
    try:
        date = parsedate_to_datetime(str(message.get("Date", "")))
        timestamp = date.isoformat() if date.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        timestamp = None
    return {
        "subject": _clean_subject(str(message.get("Subject", ""))) or None,
        "sender": _clean_subject(sender) or None,
        "timestamp": timestamp,
    }


_HISTORY_ARCHIVE_LIMIT = 64 * 1024 * 1024


def _history_archive(podman: Any, container: str, name: str) -> tuple[list[dict], bool]:
    try:
        response = podman.container_archive_get(container, f"{MAIL_ROOT}/{name}")
    except ArchivePathNotFound:
        return [], False
    with io.BytesIO() as archive:
        try:
            for chunk in response.iter_bytes():
                if archive.tell() + len(chunk) > _HISTORY_ARCHIVE_LIMIT:
                    raise MailSubjectsUnavailable("mailbox archive exceeds read limit")
                archive.write(chunk)
        finally:
            response.close()
        archive.seek(0)
        with tarfile.open(fileobj=archive, mode="r:*") as tf:
            members = tf.getmembers()
            if any(_is_maildir_layout_member(m.name) for m in members):
                messages = sorted(
                    (m for m in members if m.isreg() and _is_maildir_message(m.name)),
                    key=lambda m: (_maildir_sort_key(posixpath.basename(m.name)), m.name),
                    reverse=True,
                )
                return [_history_header(_extract(tf, m)) for m in messages[:SUBJECT_LIMIT]], len(messages) > SUBJECT_LIMIT
            regular = [m for m in members if m.isreg()]
            if not regular:
                return [], False
            if len(regular) != 1 or regular[0].size > _HISTORY_ARCHIVE_LIMIT:
                raise MailSubjectsUnavailable("unsupported mailbox archive")
            raw = _extract(tf, regular[0]).read()
            chunks = [chunk for chunk in re.split(rb"(?m)^From ", raw) if chunk.strip()]
            records = []
            for chunk in reversed(chunks[-SUBJECT_LIMIT:]):
                first, _, rest = chunk.partition(b"\n")
                headers = chunk if re.match(rb"^[!-9;-~]+:", first) else rest
                records.append(_history_header(io.BytesIO(headers)))
            return records, len(chunks) > SUBJECT_LIMIT


def read_crew_mail_history(podman: Any, container: str) -> dict:
    """Read retained deliveries without waking a stopped crew."""
    if not podman.container_exists(container):
        raise MailSubjectsUnavailable("crew container not found")
    mailboxes = {}
    capped = False
    for name in MAILBOXES:
        deliveries, limited = _history_archive(podman, container, name)
        mailboxes[name] = deliveries
        capped |= limited
    if not podman.container_exists(container):
        raise MailSubjectsUnavailable("crew container removed during read")
    return {"mailboxes": mailboxes, "capped": capped}
