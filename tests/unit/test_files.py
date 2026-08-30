"""Unit tests for ``transport.files`` — file/bundle signing + transfer handlers.

TRN-85: migration target for classes whose function-under-test is defined in
``files.py`` (``_sign_file_url``, ``_sign_upload_url``, ``_verify_file_token``,
``_handle_file_get``, ``_handle_file_put``, ``_transfer_upload``,
``_TarMemberStream``, ``_ResponseChunkReader``) and the ``evac``/``supply``
MCP transfer tools. Patch via ``transport.files`` for the owning-module
functions; patch ``server.<tool>`` at the call site for the MCP tools.

Some classes here are podman/git-gated with
``@unittest.skipUnless(shutil.which("git"), ...)`` and auto-skip when the
binary is absent.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.unit.helpers import files_mod, server  # noqa: F401


if __name__ == "__main__":
    unittest.main()
