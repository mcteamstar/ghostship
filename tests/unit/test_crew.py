"""Crew comp field persistence and legacy compatibility."""

from __future__ import annotations

import pytest

from transport import crew as crew_mod
from transport.crew import Crew


@pytest.fixture(autouse=True)
def _reset_conflict_warnings():
    crew_mod._warned_comp_conflicts.clear()
    yield
    crew_mod._warned_comp_conflicts.clear()


def test_new_crew_serialization_writes_canonical_and_legacy_fields() -> None:
    crew = Crew(
        crew_id="test-crew",
        container="gs-test-crew",
        volume="gs-vol-test-crew",
        home_volume="gs-home-test-crew",
        comp="worker",
    )

    data = crew.to_dict()

    assert data["comp"] == "worker"
    assert data["composition"] == "worker"


def test_legacy_only_record_loads_and_serializes_both_fields() -> None:
    crew = Crew.from_dict(
        "test-crew",
        {
            "container": "gs-test-crew",
            "composition": "worker",
        },
    )

    assert crew.comp == "worker"
    assert crew.to_dict()["comp"] == "worker"
    assert crew.to_dict()["composition"] == "worker"


def test_conflicting_persisted_fields_warn_and_use_comp(caplog) -> None:
    with caplog.at_level("WARNING", logger="transport.crew"):
        crew = Crew.from_dict(
            "test-crew",
            {
                "container": "gs-test-crew",
                "comp": "spec-ops",
                "composition": "worker",
            },
        )

    assert crew.comp == "spec-ops"
    assert "conflicting persisted comp and composition values" in caplog.text
    assert crew.to_dict()["comp"] == "spec-ops"
    assert crew.to_dict()["composition"] == "spec-ops"


def test_record_without_either_comp_field_uses_existing_default() -> None:
    crew = Crew.from_dict("test-crew", {"container": "gs-test-crew"})

    assert crew.comp == "spec-ops"


def test_empty_comp_falls_back_to_legacy_composition() -> None:
    crew = Crew.from_dict(
        "test-crew",
        {"container": "gs-test-crew", "comp": "", "composition": "worker"},
    )

    assert crew.comp == "worker"


def test_conflicting_record_warns_only_once(caplog) -> None:
    record = {"container": "gs-test-crew", "comp": "spec-ops", "composition": "worker"}

    with caplog.at_level("WARNING", logger="transport.crew"):
        for _ in range(3):
            assert crew_mod.comp_from_record("test-crew", record) == "spec-ops"

    assert caplog.text.count("conflicting persisted comp and composition values") == 1
