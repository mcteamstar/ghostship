"""Unit tests for Radar mailbox subjects (TRN-370), transport side.

Covers:
  - archive reader: Maildir and legacy mbox ordering, caps, truncation,
    empty mailboxes, corrupt archives, layout errors
  - stopped crews: absent admiral mailbox is empty; a removed container, a
    mid-read removal, or any other archive error is unavailable
  - running crews: exec output validation; exec failure is unavailable
  - container script: ordering, caps, missing path, unreadable file fails
  - handler: 404 unknown crew, 503 unavailable, 200 subject-only shape
  - auth: the internal path dispatches under the transport secret, not the bearer key
  - read-only: no mailbox file changes and no write-capable Podman call
"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import tarfile
import unittest
from pathlib import Path
from unittest.mock import patch

from transport import mail_subjects as ms
from transport.podman import ArchivePathNotFound

_SCRIPT = Path(__file__).parents[2] / "transport" / "container_scripts" / "read_crew_mail_subjects.py"
_MAILBOX_NAMES = list(ms.MAILBOXES)


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_script():
    spec = importlib.util.spec_from_file_location("read_crew_mail_subjects", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _msg(subject: str, body: str = "body") -> bytes:
    return (
        f"From: sender@localhost\nSubject: {subject}\n"
        f"Date: Mon, 1 Jan 2026 00:00:00 +0000\n\n{body}\n"
    ).encode()


def _maildir_tar(root: str, files: dict[str, bytes]) -> bytes:
    """Tar of a Maildir rooted at ``root``; ``files`` keys are ``new/<name>`` or ``cur/<name>``."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for dirname in (root, f"{root}/new", f"{root}/cur"):
            info = tarfile.TarInfo(dirname)
            info.type = tarfile.DIRTYPE
            tf.addfile(info)
        for rel, data in files.items():
            info = tarfile.TarInfo(f"{root}/{rel}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _file_tar(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _Archive:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def iter_bytes(self, chunk_size: int = 65536):
        for offset in range(0, len(self._data), chunk_size):
            yield self._data[offset:offset + chunk_size]

    def close(self) -> None:
        self.closed = True


class _Podman:
    """Scripted Podman surface. Records every call so tests can assert read-only use."""

    def __init__(
        self,
        *,
        exists=(True,),
        archives: dict | None = None,
        archive_errors: dict | None = None,
        exec_output: str = "{}",
        exec_error: Exception | None = None,
    ) -> None:
        self._exists = list(exists)
        self.archives = archives or {}
        self.archive_errors = archive_errors or {}
        self.exec_output = exec_output
        self.exec_error = exec_error
        self.calls: list[tuple] = []

    def container_exists(self, name):
        self.calls.append(("container_exists", name))
        return self._exists.pop(0) if len(self._exists) > 1 else self._exists[0]

    def container_archive_get(self, name, path):
        self.calls.append(("container_archive_get", name, path))
        if path in self.archive_errors:
            raise self.archive_errors[path]
        if path in self.archives:
            return _Archive(self.archives[path])
        raise ArchivePathNotFound(f"Podman archive GET failed with HTTP 404: {path}")

    def container_exec_checked(self, name, cmd, env=None):
        self.calls.append(("container_exec_checked", name, cmd))
        if self.exec_error is not None:
            raise self.exec_error
        return self.exec_output

    def write_capable_calls(self) -> list[tuple]:
        allowed = {"container_exists", "container_archive_get", "container_exec_checked"}
        return [c for c in self.calls if c[0] not in allowed]


def _all_stopped_archives(overrides: dict[str, bytes] | None = None) -> dict[str, bytes]:
    """Archives for the eight mailboxes, each with one subject, except where overridden."""
    archives = {}
    for name in _MAILBOX_NAMES:
        archives[f"/var/mail/{name}"] = _maildir_tar(name, {
            f"new/1700000000.1.{name}.host": _msg(f"{name} subject"),
        })
    archives.update(overrides or {})
    return archives


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── archive reader: Maildir ───────────────────────────────────────────────────

class TestArchiveMaildir(unittest.TestCase):

    def test_newest_first_by_filename_timestamp(self):
        tar = _maildir_tar("ghost", {
            "new/1700000001.1.a.host": _msg("oldest"),
            "new/1700000003.1.c.host": _msg("newest"),
            "cur/1700000002.1.b.host:2,S": _msg("middle"),
        })
        self.assertEqual(ms.subjects_from_archive(tar), ["newest", "middle", "oldest"])

    def test_caps_at_fifty_most_recent(self):
        files = {
            f"new/{1700000000 + i}.1.m{i}.host": _msg(f"s{i:03d}") for i in range(60)
        }
        subjects = ms._finalize(ms.subjects_from_archive(_maildir_tar("ghost", files)))
        self.assertEqual(len(subjects), 50)
        self.assertEqual(subjects[0], "s059")
        self.assertEqual(subjects[-1], "s010")

    def test_subject_truncated_to_200_characters(self):
        tar = _maildir_tar("ghost", {"new/1.1.a.host": _msg("x" * 300)})
        subjects = ms._finalize(ms.subjects_from_archive(tar))
        self.assertEqual(len(subjects[0]), 200)

    def test_folded_subject_whitespace_is_normalised(self):
        raw = b"Subject: first line\n  second line\n\nbody\n"
        tar = _maildir_tar("ghost", {"new/1.1.a.host": raw})
        self.assertEqual(ms.subjects_from_archive(tar), ["first line second line"])

    def test_messages_without_subject_are_skipped(self):
        tar = _maildir_tar("ghost", {
            "new/2.1.a.host": b"From: x\n\nno subject\n",
            "new/1.1.b.host": _msg("kept"),
        })
        self.assertEqual(ms.subjects_from_archive(tar), ["kept"])

    def test_empty_maildir_yields_empty_list(self):
        tar = _maildir_tar("ghost", {})
        self.assertEqual(ms.subjects_from_archive(tar), [])


# ── archive reader: legacy mbox ───────────────────────────────────────────────

class TestArchiveMaildirLayoutEdges(unittest.TestCase):
    """Archive reads must agree with the running-crew script on what counts as mail."""

    @staticmethod
    def _tar(entries: list[tuple[str, bytes | None]]) -> bytes:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name, data in entries:
                info = tarfile.TarInfo(name)
                if data is None:
                    info.type = tarfile.DIRTYPE
                    tf.addfile(info)
                else:
                    info.size = len(data)
                    tf.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_maildir_with_only_stale_tmp_files_is_empty(self):
        data = self._tar([
            ("ghost", None), ("ghost/new", None), ("ghost/cur", None), ("ghost/tmp", None),
            ("ghost/tmp/1.1.a.h", _msg("half delivered")),
        ])
        self.assertEqual(ms.subjects_from_archive(data), [])

    def test_maildir_with_several_tmp_files_is_not_an_unexpected_layout(self):
        data = self._tar([
            ("ghost", None), ("ghost/new", None), ("ghost/cur", None), ("ghost/tmp", None),
            ("ghost/tmp/1.1.a.h", _msg("a")), ("ghost/tmp/2.1.b.h", _msg("b")),
        ])
        self.assertEqual(ms.subjects_from_archive(data), [])

    def test_tmp_files_are_ignored_beside_delivered_mail(self):
        data = self._tar([
            ("ghost", None), ("ghost/new", None), ("ghost/tmp", None),
            ("ghost/new/5.1.a.h", _msg("delivered")),
            ("ghost/tmp/9.1.b.h", _msg("in flight")),
        ])
        self.assertEqual(ms.subjects_from_archive(data), ["delivered"])

    def test_maildir_subfolders_are_not_read(self):
        data = self._tar([
            ("ghost", None), ("ghost/new", None), ("ghost/.Sent", None), ("ghost/.Sent/new", None),
            ("ghost/new/1.1.a.h", _msg("inbox")),
            ("ghost/.Sent/new/9.1.b.h", _msg("sent folder")),
        ])
        self.assertEqual(ms.subjects_from_archive(data), ["inbox"])


class TestArchiveMbox(unittest.TestCase):

    def test_reverse_file_order_for_mbox(self):
        mbox = (
            b"From sender Mon Jan  1 00:00:00 2026\n"
            b"Subject: first\n\nbody one\n"
            b"From sender Mon Jan  1 00:00:01 2026\n"
            b"Subject: second\n\nbody two\n"
        )
        tar = _file_tar("captain", mbox)
        self.assertEqual(ms.subjects_from_archive(tar), ["second", "first"])

    def test_empty_mbox_yields_empty_list(self):
        self.assertEqual(ms.subjects_from_archive(_file_tar("captain", b"")), [])

    def test_mbox_over_cap_keeps_fifty_newest(self):
        mbox = b"".join(
            f"From sender Mon Jan  1 00:00:00 2026\nSubject: m{i}\n\nbody\n".encode()
            for i in range(55)
        )
        subjects = ms._finalize(ms.subjects_from_archive(_file_tar("admiral", mbox)))
        self.assertEqual(len(subjects), 50)
        self.assertEqual(subjects[0], "m54")


class TestArchiveCorruptLayouts(unittest.TestCase):

    def test_non_tar_bytes_are_unavailable(self):
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.subjects_from_archive(b"not a tar archive")

    def test_multiple_plain_files_outside_maildir_are_unavailable(self):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            for name in ("a", "b"):
                info = tarfile.TarInfo(name)
                info.size = 0
                tf.addfile(info, io.BytesIO(b""))
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.subjects_from_archive(buf.getvalue())


# ── stopped crews ─────────────────────────────────────────────────────────────

class TestStoppedCrew(unittest.TestCase):

    def test_reads_all_eight_mailboxes(self):
        podman = _Podman(archives=_all_stopped_archives())
        result = ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)
        self.assertEqual(sorted(result), sorted(_MAILBOX_NAMES))
        self.assertEqual(result["ghost"], ["ghost subject"])

    def test_admiral_never_created_is_empty_not_unavailable(self):
        archives = _all_stopped_archives()
        del archives["/var/mail/admiral"]
        podman = _Podman(archives=archives)
        result = ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)
        self.assertEqual(result["admiral"], [])
        self.assertEqual(result["ghost"], ["ghost subject"])

    def test_removed_container_is_unavailable_without_archive_reads(self):
        podman = _Podman(exists=(False,), archives=_all_stopped_archives())
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-gone", running=False)
        self.assertFalse(any(c[0] == "container_archive_get" for c in podman.calls))

    def test_container_removed_mid_read_is_unavailable(self):
        podman = _Podman(exists=(True, False), archives=_all_stopped_archives())
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)

    def test_other_archive_error_fails_whole_request(self):
        overrides = {}
        podman = _Podman(
            archives=_all_stopped_archives(overrides),
            archive_errors={"/var/mail/captain": RuntimeError("HTTP 500")},
        )
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)

    def test_corrupt_mailbox_archive_fails_whole_request(self):
        archives = _all_stopped_archives({"/var/mail/raven": b"garbage"})
        podman = _Podman(archives=archives)
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)

    def test_read_is_read_only(self):
        podman = _Podman(archives=_all_stopped_archives())
        ms.read_crew_mail_subjects(podman, "gs-alpha", running=False)
        self.assertEqual(podman.write_capable_calls(), [])
        self.assertFalse(any(c[0] == "container_exec_checked" for c in podman.calls))


# ── running crews ─────────────────────────────────────────────────────────────

def _exec_payload(**overrides) -> str:
    data = {name: [f"{name} subject"] for name in _MAILBOX_NAMES}
    data.update(overrides)
    return json.dumps(data)


class TestRunningCrew(unittest.TestCase):

    def test_exec_output_is_parsed_per_mailbox(self):
        podman = _Podman(exec_output=_exec_payload())
        result = ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)
        self.assertEqual(result["spectre"], ["spectre subject"])

    def test_exec_runs_the_crew_script_with_mailbox_list(self):
        podman = _Podman(exec_output=_exec_payload())
        ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)
        name, cmd = podman.calls[0][1], podman.calls[0][2]
        self.assertEqual(name, "gs-alpha")
        self.assertEqual(cmd[0], "python3")
        self.assertTrue(cmd[1].endswith("/read_crew_mail_subjects.py"))
        self.assertEqual(json.loads(cmd[2]), _MAILBOX_NAMES)

    def test_exec_failure_is_unavailable(self):
        podman = _Podman(exec_error=RuntimeError("no such container"))
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)

    def test_unparseable_output_is_unavailable(self):
        podman = _Podman(exec_output="<html>not json</html>")
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)

    def test_missing_mailbox_key_is_unavailable(self):
        data = {name: [] for name in _MAILBOX_NAMES if name != "admiral"}
        podman = _Podman(exec_output=json.dumps(data))
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)

    def test_non_string_subject_is_unavailable(self):
        podman = _Podman(exec_output=_exec_payload(ghost=[{"subject": "x"}]))
        with self.assertRaises(ms.MailSubjectsUnavailable):
            ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)

    def test_exec_output_is_capped_and_truncated(self):
        long_list = ["y" * 300] * 60
        podman = _Podman(exec_output=_exec_payload(ghost=long_list))
        result = ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)
        self.assertEqual(len(result["ghost"]), 50)
        self.assertEqual(len(result["ghost"][0]), 200)

    def test_running_read_is_read_only(self):
        podman = _Podman(exec_output=_exec_payload())
        ms.read_crew_mail_subjects(podman, "gs-alpha", running=True)
        self.assertEqual(podman.write_capable_calls(), [])


# ── container script ──────────────────────────────────────────────────────────

class TestContainerScript(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.script = _load_script()

    def tearDown(self):
        self._tmp.cleanup()

    def _maildir(self, name, files):
        base = self.root / name
        (base / "new").mkdir(parents=True)
        (base / "cur").mkdir(parents=True)
        for rel, data in files.items():
            (base / rel).write_bytes(data)

    def test_maildir_newest_first_and_mbox_reverse(self):
        self._maildir("ghost", {
            "new/1700000001.1.a.h": _msg("old"),
            "cur/1700000002.1.b.h:2,S": _msg("new"),
        })
        (self.root / "captain").write_bytes(
            b"From s Mon Jan 1 00:00:00 2026\nSubject: c1\n\nb\n"
            b"From s Mon Jan 1 00:00:01 2026\nSubject: c2\n\nb\n"
        )
        result = self.script.read_subjects(["ghost", "captain"], root=str(self.root))
        self.assertEqual(result["ghost"], ["new", "old"])
        self.assertEqual(result["captain"], ["c2", "c1"])

    def test_missing_mailbox_path_is_empty(self):
        result = self.script.read_subjects(["admiral"], root=str(self.root))
        self.assertEqual(result, {"admiral": []})

    def test_cap_and_truncation(self):
        self._maildir("ghost", {
            f"new/{1700000000 + i}.1.m{i}.h": _msg("z" * 400) for i in range(60)
        })
        result = self.script.read_subjects(["ghost"], root=str(self.root))
        self.assertEqual(len(result["ghost"]), 50)
        self.assertEqual(len(result["ghost"][0]), 200)

    def test_unreadable_entry_raises_os_error(self):
        self._maildir("ghost", {"new/1.1.a.h": _msg("ok")})
        # A directory named like a message makes open() fail, which must not
        # be silently skipped: the caller would report a false, partial result.
        (self.root / "ghost" / "new" / "2.1.bad").mkdir()
        with self.assertRaises(OSError):
            self.script.read_subjects(["ghost"], root=str(self.root))

    def test_message_renamed_mid_scan_is_retried(self):
        self._maildir("ghost", {"new/1700000001.1.a.h": _msg("moved")})
        real_once = self.script._maildir_subjects_once
        calls = {"n": 0}

        def flaky(path):
            calls["n"] += 1
            if calls["n"] == 1:
                raise FileNotFoundError("renamed from new/ to cur/")
            return real_once(path)

        self.script._maildir_subjects_once = flaky
        result = self.script.read_subjects(["ghost"], root=str(self.root))
        self.assertEqual(result["ghost"], ["moved"])
        self.assertEqual(calls["n"], 2)

    def test_persistently_missing_file_still_raises(self):
        self._maildir("ghost", {"new/1.1.a.h": _msg("ok")})

        def always_missing(path):
            raise FileNotFoundError("gone")

        self.script._maildir_subjects_once = always_missing
        with self.assertRaises(OSError):
            self.script.read_subjects(["ghost"], root=str(self.root))

    def test_script_is_read_only(self):
        self._maildir("ghost", {"new/1.1.a.h": _msg("keep me")})
        target = self.root / "ghost" / "new" / "1.1.a.h"
        before = (target.read_bytes(), target.stat().st_mtime_ns)
        self.script.read_subjects(["ghost"], root=str(self.root))
        self.assertEqual((target.read_bytes(), target.stat().st_mtime_ns), before)


# ── handler and auth ──────────────────────────────────────────────────────────

def _import_server():
    try:
        import server as _s
    except ModuleNotFoundError:
        from transport import server as _s
    return _s


def _handler_call(crew_id: str, *, registry_info, podman=None, reader=None):
    """Invoke the mail-subjects handler directly and return (status, json_body)."""
    _s = _import_server()
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": f"/internal/crews/{crew_id}/mail-subjects",
        "query_string": b"",
        "headers": [],
    }
    messages: list[dict] = []

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message):
        messages.append(message)

    def _fake_get_crew(cid):
        if registry_info is None:
            raise KeyError(cid)
        return registry_info

    patches = [
        patch.object(_s, "_get_crew", side_effect=_fake_get_crew),
        patch("transport.podman._get_podman", return_value=podman or _Podman()),
    ]
    if reader is not None:
        patches.append(patch("transport.mail_subjects.read_crew_mail_subjects", side_effect=reader))

    async def _invoke():
        req = Request(scope, _receive)
        resp = await _s._handle_internal_crew_mail_subjects_get(req)
        await resp(scope, _receive, _send)

    for p in patches:
        p.start()
    try:
        _run(_invoke())
    finally:
        for p in patches:
            p.stop()

    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


class TestHandler(unittest.TestCase):

    def test_unknown_crew_returns_404(self):
        status, body = _handler_call("nope", registry_info=None)
        self.assertEqual(status, 404)
        self.assertIn("error", body)
        self.assertNotIn("mailboxes", body)

    def test_unavailable_source_returns_503_without_mailbox_data(self):
        info = {"container": "gs-alpha", "status": "running"}
        podman = _Podman(exec_error=RuntimeError("boom"))
        status, body = _handler_call("alpha", registry_info=info, podman=podman)
        self.assertEqual(status, 503)
        self.assertEqual(body, {"error": "mail subjects unavailable"})

    def test_running_crew_uses_exec_path(self):
        info = {"container": "gs-alpha", "status": "running"}
        podman = _Podman(exec_output=_exec_payload())
        status, body = _handler_call("alpha", registry_info=info, podman=podman)
        self.assertEqual(status, 200)
        self.assertTrue(any(c[0] == "container_exec_checked" for c in podman.calls))
        self.assertFalse(any(c[0] == "container_archive_get" for c in podman.calls))

    def test_stopped_crew_uses_archive_path_without_starting_it(self):
        info = {"container": "gs-alpha", "status": "stopped"}
        podman = _Podman(archives=_all_stopped_archives())
        status, body = _handler_call("alpha", registry_info=info, podman=podman)
        self.assertEqual(status, 200)
        self.assertFalse(any(c[0] == "container_exec_checked" for c in podman.calls))
        self.assertEqual(podman.write_capable_calls(), [])

    def test_response_contains_mailbox_names_and_subject_strings_only(self):
        info = {"container": "gs-alpha", "status": "stopped"}
        archives = _all_stopped_archives()
        archives["/var/mail/ghost"] = _maildir_tar("ghost", {
            "new/1700000000.1.a.h": b"From: secret@localhost\nTo: x@localhost\n"
                                    b"Date: Mon, 1 Jan 2026 00:00:00 +0000\n"
                                    b"Subject: hello\n\nSECRET BODY TEXT\n",
        })
        status, body = _handler_call("alpha", registry_info=info, podman=_Podman(archives=archives))
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"mailboxes"})
        self.assertEqual(set(body["mailboxes"]), set(_MAILBOX_NAMES))
        for subjects in body["mailboxes"].values():
            self.assertIsInstance(subjects, list)
            self.assertTrue(all(isinstance(s, str) for s in subjects))
        self.assertEqual(body["mailboxes"]["ghost"], ["hello"])
        self.assertNotIn("SECRET BODY TEXT", json.dumps(body))
        self.assertNotIn("secret@localhost", json.dumps(body))


class TestInternalRouteAuth(unittest.TestCase):
    """The internal path dispatches on the transport secret, with no bearer key."""

    def _app(self):
        from transport.auth import BearerAuthMiddleware, TransportSecretMiddleware
        from starlette.responses import JSONResponse

        async def _handler(request):
            return JSONResponse({"mailboxes": {}})

        async def _inner(scope, receive, send):
            raise AssertionError("bearer app must not receive the internal route")

        bearer = BearerAuthMiddleware(
            _inner,
            api_key="operator-key",
            public_routes={("GET", "/internal/crews/*/mail-subjects"): _handler},
        )
        return TransportSecretMiddleware(bearer, transport_secret="portal-secret")

    def _request(self, app, headers):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/internal/crews/alpha/mail-subjects",
            "query_string": b"",
            "headers": headers,
        }
        messages: list[dict] = []

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(message):
            messages.append(message)

        _run(app(scope, _receive, _send))
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, body

    def test_missing_transport_token_returns_no_mailbox_data(self):
        status, body = self._request(self._app(), headers=[])
        self.assertEqual(status, 401)
        self.assertNotIn(b"mailboxes", body)

    def test_wrong_transport_token_returns_no_mailbox_data(self):
        status, body = self._request(
            self._app(), headers=[(b"x-transport-token", b"wrong")]
        )
        self.assertEqual(status, 401)
        self.assertNotIn(b"mailboxes", body)

    def test_valid_transport_token_reaches_handler_without_bearer_key(self):
        status, body = self._request(
            self._app(), headers=[(b"x-transport-token", b"portal-secret")]
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"mailboxes": {}})


if __name__ == "__main__":
    unittest.main()
