"""Pytest configuration for the test suite."""
import pytest
from unittest.mock import patch


def pytest_configure(config):
    """Register custom marks so pytest doesn't warn about unknown markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )


@pytest.fixture(autouse=True)
def _patch_registry_io(request):
    """Prevent unit tests from writing to /data.

    CrewRegistry.__enter__ calls registry._load_registry() and __exit__ calls
    registry._save_registry(). Without these patches any test that exercises a
    'with registry:' block would attempt to access /data, which does not exist
    in the CI environment.

    Tests in test_registry.py test registry internals directly (real file I/O
    under a tmpdir) and are excluded from this fixture. All other unit tests
    get a safe default: empty registry and no-op save.

    Tests that need a specific registry state patch _registry_mod._load_registry
    individually (with return_value=<their dict>); those per-test patches take
    precedence over this autouse fixture.
    """
    # Skip for registry-focused tests that exercise real file I/O
    if "test_registry" in request.fspath.basename or "test_batch" in request.fspath.basename:
        yield
        return

    import transport.registry as _registry_mod
    with (
        patch.object(_registry_mod, "_load_registry", return_value={"crews": {}}),
        patch.object(_registry_mod, "_save_registry"),
    ):
        yield
