"""Pytest configuration for the test suite."""
import pytest


def pytest_configure(config):
    """Register custom marks so pytest doesn't warn about unknown markers."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    )
