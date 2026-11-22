"""Pytest fixtures shared by the transport unit test suite."""

from __future__ import annotations

import pytest

from tests.fakes import FakePodmanClient


# ── Pytest marks ─────────────────────────────────────────────────────────────

def pytest_configure(config):
    # "slow" marker removed in TRN-296 — no tests carry that mark any more.
    config.addinivalue_line("markers", "integration: marks integration tests")


# ── Shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture
def fake_podman() -> FakePodmanClient:
    """Return a fresh FakePodmanClient with no scripted state."""
    return FakePodmanClient()


@pytest.fixture
def fake_podman_with_sentinel(tmp_path):
    """Return a FakePodmanClient pre-scripted with a sentinel file.

    The sentinel content is ``captain_id=test-crew\\ncompleted_at=2026-01-01T00:00:00Z\\n``
    and the container is named ``gs-test-crew``.
    """
    podman = FakePodmanClient()
    sentinel_content = b"captain_id=test-crew\ncompleted_at=2026-01-01T00:00:00Z\nreason=standing orders met\n"
    podman.set_archive_file(
        container="gs-test-crew",
        path="/home/kirocrew/workplace/kirocrew-workspace/.captain_done",
        content=sentinel_content,
        filename=".captain_done",
    )
    return podman


@pytest.fixture
def make_task_service():
    """Build an isolated service, with individual collaborators overridable."""
    from types import SimpleNamespace

    from transport.lifecycle import _validate_agent
    from transport.task_service import TaskService

    def make(call_gateway, *, crew=None, **overrides):
        if crew is None:
            crew = {"container": "gs-test-crew", "enrolled_agents": []}
        dependencies = {
            "config": SimpleNamespace(
                ga_batch_max_tasks=5, ga_pickup_max_poll_secs=30, ga_task_timestamp_ttl_secs=60,
            ),
            "require_crew": lambda _: crew,
            "ensure_running": lambda record, _: record,
            "to_crew": lambda *_: SimpleNamespace(container=crew["container"]),
            "validate_agent": _validate_agent,
            "call_gateway": call_gateway,
            "get_podman": lambda: None,
            "sign_in": lambda: SimpleNamespace(dispatch_guard=lambda *_: None),
            "record_last_task_at": lambda *_: None,
            "write_batch": lambda *_args, **_kwargs: None,
            "find_batch": lambda *_: None,
            "update_batch_status": lambda *_: None,
            "read_mail_counts": lambda *_: {},
            "read_mail_subjects": lambda *_: {},
        }
        dependencies.update(overrides)
        return TaskService(**dependencies)

    return make
