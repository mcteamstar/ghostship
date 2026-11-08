"""TRN-312: preserve KiroCrew's unreadable signing-key mask on Linux.

The legacy remount resolves a mode-000 stand-in by path and can fail EACCES.
mount_setattr through O_PATH sets only read-only, retaining every other mount
restriction. This compatibility patch is pinned to the exact upstream block:
a base-image update that changes it must be reviewed rather than silently
skipping the credential seal. Remove once the base image carries the fix.
"""
from importlib.util import find_spec
from pathlib import Path

ORIGINAL = '''                _mount_or_die(
                    launch,
                    f.encode(),
                    f.encode(),
                    _MS_REMOUNT | _MS_BIND | _MS_RDONLY | _locked_mount_flags(f.encode()),
                    "sealing unreadable mask %s" % f,
                )'''
REPLACEMENT = '''                # TRN-312: seal the mounted mode-000 inode by descriptor.
                # attr_set=RDONLY, attr_clr=0 preserves all existing mount flags.
                # Never fall back to leaving a writable/unsealed stand-in.
                if _plat.machine() not in ("x86_64", "aarch64"):
                    sys.exit("sandbox: BLOCKED -- unsupported mount_setattr architecture")
                _seal_fd = os.open(f, os.O_PATH | os.O_NOFOLLOW)
                try:
                    _attrs = (ctypes.c_uint64 * 4)(1, 0, 0, 0)
                    if launch.libc.syscall(
                        442, _seal_fd, b"", 0x1000,
                        ctypes.byref(_attrs), ctypes.sizeof(_attrs),
                    ) != 0:
                        sys.exit(
                            "sandbox: BLOCKED -- sealing unreadable mask %s "
                            "with mount_setattr failed: errno %d" % (f, ctypes.get_errno())
                        )
                finally:
                    os.close(_seal_fd)'''


def patch(source: str) -> str:
    if source.count(ORIGINAL) != 1:
        raise RuntimeError("KiroCrew sandbox seal changed; review TRN-312 compatibility patch")
    return source.replace(ORIGINAL, REPLACEMENT, 1)


if __name__ == "__main__":
    spec = find_spec("kiro_crew.sandbox_launcher_parts.mask_stages")
    if spec is None or spec.origin is None:
        raise RuntimeError("KiroCrew sandbox mask module not found")
    target = Path(spec.origin)
    target.write_text(patch(target.read_text()))
