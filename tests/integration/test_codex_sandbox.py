"""Run inside the spec-ops image as kirocrew; uses a disposable dummy key only.

Example: podman --connection ghost-academy run --rm -i --security-opt
no-new-privileges --cap-drop SYS_ADMIN --cap-drop NET_RAW --entrypoint python3
localhost/spec-ops:latest - < tests/integration/test_codex_sandbox.py
"""
from pathlib import Path
import errno
import subprocess
import sys
import textwrap

def main():
    from kiro_crew.sandbox_wrap import wrap_argv

    key = Path.home() / '.kiro/crew/token_signing.key'
    key.parent.mkdir(parents=True, exist_ok=True)
    if key.exists():
        raise RuntimeError('Refusing to overwrite an existing signing key; use a disposable container')
    key.write_text('dummy-test-key')
    child = textwrap.dedent('''
    from pathlib import Path
    import os, errno
    key = Path.home() / '.kiro/crew/token_signing.key'
    for operation in (lambda: key.read_text(), lambda: os.chmod(key, 0o600), lambda: key.write_text('changed')):
        try:
            operation()
        except OSError as error:
            assert error.errno in (errno.EACCES, errno.EPERM, errno.EROFS), error
        else:
            raise AssertionError('Signing-key mask was readable or writable')
    print('MASK_READ_WRITE_CHMOD_DENIED')
    ''')
    argv, cleanup = wrap_argv([sys.executable, '-c', child], mode='auto')
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stderr
        assert 'MASK_READ_WRITE_CHMOD_DENIED' in result.stdout, result.stdout
        assert key.read_text() == 'dummy-test-key', 'Original signing key changed'
        # A missing/denied sealing syscall must refuse to launch the child.
        assert cleanup, 'Expected namespace launcher file'
        launcher = Path(cleanup)
        source = launcher.read_text()
        assert source.count('442, _seal_fd') == 1
        launcher.write_text(source.replace('442, _seal_fd', '-1, _seal_fd', 1))
        failed = subprocess.run(argv, capture_output=True, text=True, timeout=20)
        assert failed.returncode != 0, 'Sealing syscall failure was ignored'
        assert 'mount_setattr failed' in failed.stderr, failed.stderr
        assert 'MASK_READ_WRITE_CHMOD_DENIED' not in failed.stdout
        assert key.read_text() == 'dummy-test-key'
        print('Sandbox isolation and fail-closed sealing verified')
    finally:
        if cleanup:
            Path(cleanup).unlink(missing_ok=True)
        key.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
