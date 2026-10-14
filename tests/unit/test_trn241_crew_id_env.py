"""TRN-241: KIROCREW_CREW_ID must be injected into the crew container env.

The Raven self-cancel script reads $KIROCREW_CREW_ID to construct the
transport URL. If the var is absent the URL has an empty path segment and
the request fails with 401 before reaching the endpoint.
"""
import re
import unittest


class TestKirocrewCrewIdInjection(unittest.TestCase):
    """KIROCREW_CREW_ID is set in server.py container_env alongside KIROCREW_CORS_ORIGINS."""

    def test_kirocrew_crew_id_in_server_source(self) -> None:
        """server.py must assign KIROCREW_CREW_ID to container_env in the launch path."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent.parent
               / "transport" / "server.py").read_text()
        # The assignment must appear in the container_env dict literal,
        # near KIROCREW_CORS_ORIGINS.
        self.assertIn(
            '"KIROCREW_CREW_ID"',
            src,
            "server.py must set KIROCREW_CREW_ID in the crew container environment",
        )

    def test_kirocrew_crew_id_assigned_with_crew_id_value(self) -> None:
        """KIROCREW_CREW_ID must be set to the crew_id variable, not a constant."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent.parent
               / "transport" / "server.py").read_text()
        # Match: "KIROCREW_CREW_ID": crew_id  (with optional whitespace/newline)
        pattern = re.compile(r'"KIROCREW_CREW_ID"\s*:\s*crew_id\b')
        self.assertRegex(
            src,
            pattern,
            'server.py must map "KIROCREW_CREW_ID" to the crew_id variable',
        )

    def test_kirocrew_crew_id_adjacent_to_cors_origins(self) -> None:
        """KIROCREW_CREW_ID should be set in the same container_env block as KIROCREW_CORS_ORIGINS."""
        import pathlib
        src = (pathlib.Path(__file__).resolve().parent.parent.parent
               / "transport" / "server.py").read_text()
        cors_pos = src.find('"KIROCREW_CORS_ORIGINS"')
        crew_id_pos = src.find('"KIROCREW_CREW_ID"')
        self.assertGreater(cors_pos, 0, "KIROCREW_CORS_ORIGINS must be in server.py")
        self.assertGreater(crew_id_pos, 0, "KIROCREW_CREW_ID must be in server.py")
        # They should be within 500 characters of each other (same dict block).
        self.assertLess(
            abs(cors_pos - crew_id_pos),
            500,
            "KIROCREW_CREW_ID should be set near KIROCREW_CORS_ORIGINS in the same env dict",
        )


if __name__ == "__main__":
    unittest.main()
