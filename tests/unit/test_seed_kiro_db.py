"""CI regression guard for crews/_base/graduation/seed_kiro_db.py.

Verifies that the pre-seeded kiro-cli DB produced by seed_kiro_db.py matches
the migration count and max_version expected for the pinned base image.

Expected result for KiroCrew 0.9.0-insider.4 / kiro-cli 2.29.0: (count, max_version) == (6, 5).

Marked @pytest.mark.slow — requires a running Podman daemon and pulls the base
image on first run. Excluded from the default fast unit run; add to a separate
CI step with:
    python -m pytest tests/unit/test_seed_kiro_db.py -m slow
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import unittest

import pytest


# Hard-coded expected values verified 2026-10-09 against the 0.8.0 base image.
EXPECTED_COUNT = 6
EXPECTED_MAX_VERSION = 5

# Path to the graduation seed script relative to the repo root.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SEED_SCRIPT = _REPO_ROOT / "crews" / "_base" / "graduation" / "seed_kiro_db.py"
_ADMISSION_CONTAINERFILE = (
    _REPO_ROOT / "crews" / "_base" / "admission" / "Containerfile"
)


def _parse_base_image(containerfile: pathlib.Path) -> str:
    """Extract the FROM image tag from an admission Containerfile.

    Handles two Dockerfile patterns:

    1. Direct FROM line::

           FROM ghcr.io/kirodotdev/kirocrew:<tag>
           FROM ghcr.io/kirodotdev/kirocrew@sha256:<digest>

    2. Build-arg indirection (current pattern used to support ``--build-arg``
       overrides from ``install.sh``)::

           ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew:<tag>
           ARG KC_BASE_IMAGE=ghcr.io/kirodotdev/kirocrew@sha256:<digest>
           FROM ${KC_BASE_IMAGE}

    The reference may be either a ``:<tag>`` or an immutable
    ``@sha256:<digest>`` form (TRN-219 pins by digest).

    Returns the full image reference (e.g.
    ``ghcr.io/kirodotdev/kirocrew:0.8.0`` or
    ``ghcr.io/kirodotdev/kirocrew@sha256:f4f4...``).

    Raises ValueError if no matching reference can be found.
    """
    text = containerfile.read_text()
    lines = text.splitlines()

    # Image reference: ghcr.io/kirodotdev/kirocrew followed by either a
    # :<tag> or an @sha256:<digest> suffix.
    _ref = r"ghcr\.io/kirodotdev/kirocrew(?::[^\s]+|@sha256:[0-9a-f]+)"

    # Pattern 1: direct FROM <ref>
    direct_pattern = re.compile(
        rf"^\s*FROM\s+({_ref})", re.IGNORECASE
    )
    for line in lines:
        m = direct_pattern.match(line)
        if m:
            return m.group(1)

    # Pattern 2: ARG KC_BASE_IMAGE=<ref>
    # followed by FROM ${KC_BASE_IMAGE} (or similar variable reference).
    arg_pattern = re.compile(
        rf"^\s*ARG\s+KC_BASE_IMAGE=({_ref})",
        re.IGNORECASE,
    )
    for line in lines:
        m = arg_pattern.match(line)
        if m:
            return m.group(1)

    raise ValueError(
        f"No FROM ghcr.io/kirodotdev/kirocrew:<tag> line found in {containerfile}"
    )


@pytest.mark.slow
@unittest.skipUnless(shutil.which("podman"), "requires podman")
class SeedKiroDbRegressionTests(unittest.TestCase):
    """Regression guard: seed_kiro_db.py produces the expected migration count.

    Runs the seed script inside a throwaway container sourced from the pinned
    base image, then queries the resulting DB to assert (count, max_version).
    """

    def setUp(self) -> None:
        self.image = _parse_base_image(_ADMISSION_CONTAINERFILE)

    def test_seed_produces_expected_migration_count(self) -> None:
        """seed_kiro_db.py in a throwaway 0.8.0 container yields (6, 5)."""
        # Run the seed script then query the DB — all in one container exec.
        query = (
            "python3 /tmp/seed_kiro_db.py && "
            "python3 -c \""
            "import sqlite3; "
            "c = sqlite3.connect('/home/kirocrew/.local/share/kiro-cli/data.sqlite3'); "
            "print(c.execute('SELECT COUNT(*), MAX(version) FROM migrations').fetchone())"
            "\""
        )
        result = subprocess.run(
            [
                "podman", "run", "--rm",
                "--entrypoint", "/bin/bash",
                "-v", f"{_SEED_SCRIPT}:/tmp/seed_kiro_db.py:ro",
                self.image,
                "-c", query,
            ],
            capture_output=True,
            text=True,
            timeout=300,  # image pull can be slow on first run
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"Container run failed.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        # The last line of stdout is the tuple printed by the query.
        output_line = result.stdout.strip().splitlines()[-1]
        # Parse "(6, 5)" → (6, 5)
        m = re.match(r"\((\d+),\s*(\d+)\)", output_line)
        self.assertIsNotNone(
            m,
            msg=f"Unexpected output format from migration query: {output_line!r}",
        )
        count = int(m.group(1))
        max_version = int(m.group(2))
        self.assertEqual(
            (count, max_version),
            (EXPECTED_COUNT, EXPECTED_MAX_VERSION),
            msg=(
                f"Migration count/max_version mismatch for image {self.image}. "
                f"Got ({count}, {max_version}), expected "
                f"({EXPECTED_COUNT}, {EXPECTED_MAX_VERSION}). "
                "Update seed_kiro_db.py to match the current kiro-cli schema."
            ),
        )


if __name__ == "__main__":
    unittest.main()
