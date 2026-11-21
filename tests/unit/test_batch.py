"""TaskService dispatch and pickup outcomes, including persisted batches."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import httpx2 as httpx
import pytest

from transport import registry
from transport import task_service
from transport.crew_gateway import CrewUnresponsiveError


def gateway_refusal(status, body):
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=None, response=SimpleNamespace(status_code=status, text=body),
    )


@pytest.mark.parametrize(
    "enrolled,slot,expected",
    [(True, None, "ghost"), (False, None, None), (True, False, None),
     (True, True, "ghost"), (False, True, None)],
)
def test_dispatch_slots(make_task_service, caplog, enrolled, slot, expected):
    crew = {"container": "gs-test-crew", "enrolled_agents": ["ghost"] if enrolled else []}
    gateway = Mock(side_effect=[{"id": "single"}, {"id": "first"}, {"id": "second"}])
    write_batch = Mock()
    service = make_task_service(gateway, crew=crew, write_batch=write_batch)

    single = service.dispatch(task="solo", crew_id="test-crew", slot=slot, model="model-1")
    batched = service.dispatch(tasks=["first", "second"], crew_id="test-crew", slot=slot, model="model-1")

    assert single["slot"] == batched["slot"] == expected
    assert single["task_id"] == "single"
    assert batched["status"] == "dispatched"
    assert batched["task_ids"] == ["first", "second"]
    assert batched["crew_id"] == "test-crew" and batched["agent"] == "ghost"
    assert isinstance(batched["batch_id"], str) and batched["batch_id"]
    write_batch.assert_called_once_with(
        "test-crew", batched["batch_id"], ["first", "second"],
        status="pending", created_at=batched["created_at"],
    )
    for request, task in zip(gateway.call_args_list, ("solo", "first", "second"), strict=True):
        assert request.args == (crew, "test-crew", "POST", "/api/spawn")
        payload = {"task": task, "agent": "ghost", "keep": True, "model": "model-1"}
        if expected:
            payload["parent_session"] = "dashboard:member-ghost"
        assert request.kwargs["json"] == payload
    assert ("slot=True" in caplog.text) == (slot is True)


@pytest.mark.parametrize(
    "refusal,diagnostic",
    [(CrewUnresponsiveError("gateway down"), "gateway down"),
     ({}, "spawn returned no task id"),
     (gateway_refusal(422, "refused Authorization: Bearer bearer-secret gs_csrf=csrf-secret"), "HTTP 422")],
)
def test_batch_partial_acceptance(make_task_service, refusal, diagnostic):
    gateway = Mock(side_effect=[{"id": "accepted-id"}, refusal])
    write_batch = Mock()
    service = make_task_service(gateway, write_batch=write_batch)

    result = service.dispatch(tasks=["first", "second", "third"], crew_id="test-crew")

    assert result["status"] == "partial"
    assert result["task_ids"] == ["accepted-id"]
    assert diagnostic in result["error"]
    if diagnostic == "HTTP 422":
        assert "[redacted]" in result["error"]
        assert "bearer-secret" not in result["error"] and "csrf-secret" not in result["error"]
    write_batch.assert_called_once_with(
        "test-crew", result["batch_id"], ["accepted-id"],
        status="partial", created_at=result["created_at"],
    )
    assert gateway.call_count == 2


def test_first_refusal_has_no_batch_and_redacts_credentials(make_task_service):
    gateway = Mock(side_effect=gateway_refusal(
        422, "refused crew-cookie-secret mc_token_9777=port-secret gs_session=session-secret",
    ))
    write_batch = Mock()
    service = make_task_service(gateway, crew={"cookie": "crew-cookie-secret"}, write_batch=write_batch)

    result = service.dispatch(tasks=["first", "second"], crew_id="test-crew")

    assert set(result) == {"error"}
    assert "HTTP 422" in result["error"] and "[redacted]" in result["error"]
    assert all(secret not in result["error"] for secret in ("crew-cookie-secret", "port-secret", "session-secret"))
    gateway.assert_called_once()
    write_batch.assert_not_called()


@pytest.mark.parametrize(
    "args,diagnostic",
    [({}, "Provide task or tasks"), ({"task": "x", "tasks": ["y", "z"]}, "not both"),
     ({"tasks": []}, "at least 2"), ({"tasks": ["one"]}, "at least 2"),
     ({"tasks": ["one"] * 6}, "maximum batch size of 5")],
)
def test_dispatch_validates_before_gateway(make_task_service, args, diagnostic):
    gateway = Mock()
    result = make_task_service(gateway).dispatch(crew_id="test-crew", **args)
    assert diagnostic in result["error"]
    gateway.assert_not_called()


@pytest.mark.parametrize(
    "arguments,failure",
    [({"task": "single"}, KeyError("crew not found")),
     ({"tasks": ["first", "second"]}, ValueError("crew not found")),
     ({"task": "single"}, CrewUnresponsiveError("gateway unreachable"))],
)
def test_dispatch_errors_keep_structured_shape(make_task_service, arguments, failure):
    gateway = Mock(side_effect=failure)
    lookup_fails = isinstance(failure, (KeyError, ValueError))
    dependencies = {"require_crew": Mock(side_effect=failure)} if lookup_fails else {}
    service = make_task_service(gateway, **dependencies)

    result = service.dispatch(crew_id="test-crew", **arguments)

    assert result == {"error": str(failure)}
    if lookup_fails:
        gateway.assert_not_called()
    else:
        gateway.assert_called_once()


@pytest.mark.parametrize("partial", [False, True])
def test_accepted_batch_can_be_completed_via_registry(make_task_service, monkeypatch, partial):
    crew = {"container": "gs-test-crew"}
    backing = {"crews": {"test-crew": crew}}
    monkeypatch.setattr(registry, "_load_registry", lambda: backing)
    monkeypatch.setattr(registry, "_save_registry", lambda _: None)
    accepted_ids = ["worker"] if partial else ["worker", "another-worker"]
    gateway = Mock(side_effect=[
        {"id": "worker"},
        gateway_refusal(422, "later spawn refused") if partial else {"id": "another-worker"},
        *({"id": task_id, "done": True, "elapsed": 2} for task_id in accepted_ids),
    ])
    service = make_task_service(
        gateway, crew=crew, write_batch=registry._write_batch,
        find_batch=registry._find_batch_by_task_ids,
        update_batch_status=registry._update_batch_status,
    )

    dispatched = service.dispatch(tasks=["first", "second"], crew_id="test-crew")
    batch_id = dispatched["batch_id"]
    assert dispatched["task_ids"] == accepted_ids
    records = crew["batches"]
    assert [(row["batch_id"], row["task_ids"], row["status"]) for row in records] == [
        (batch_id, accepted_ids, "partial" if partial else "pending"),
    ]
    pickup = service.pickup(crew_id="test-crew", task_ids=accepted_ids)
    assert pickup["done"] and pickup["total_tasks"] == pickup["completed_tasks"] == len(accepted_ids)
    for task_id in accepted_ids:
        assert pickup[task_id]["created_at"] and pickup[task_id]["completed_at"]
    assert records[0]["status"] == "complete"


@pytest.mark.parametrize(
    "timeout,mail_arrives,expected_reason",
    [(0, False, None), (60, False, "timeout"), (60, True, "admiral_mail")],
)
def test_batch_pickup_wait_modes(make_task_service, monkeypatch, timeout, mail_arrives, expected_reason):
    gateway = Mock(side_effect=lambda _c, _id, _method, path: {
        "id": path.rsplit("/", 1)[-1], "done": path.endswith("/finished"),
    })
    now = [0.0]

    def sleep(seconds):
        now[0] += seconds

    sleeper = Mock(side_effect=sleep)
    monkeypatch.setattr(task_service, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleeper))

    def mail_counts(*_):
        return {"admiral": int(mail_arrives and gateway.call_count > 0)}

    service = make_task_service(gateway, read_mail_counts=mail_counts)
    result = service.pickup(crew_id="test-crew", task_ids=["finished", "pending"], timeout_secs=timeout)

    assert result.get("reason") == expected_reason
    assert not result["done"] and result["total_tasks"] == 2 and result["completed_tasks"] == 1
    assert result["finished"]["done"] and not result["pending"]["done"]
    if expected_reason == "timeout":
        assert now[0] == 30
    else:
        sleeper.assert_not_called()
        assert gateway.call_count == 2


@pytest.mark.parametrize("failure", [gateway_refusal(404, "missing"), CrewUnresponsiveError("404 not found")])
def test_missing_batch_member_preserves_other_result(make_task_service, failure):
    gateway = Mock(side_effect=[{"id": "known", "done": True}, failure])
    service = make_task_service(gateway)
    result = service.pickup(crew_id="test-crew", task_ids=["known", "missing"])

    assert not result["done"] and result["completed_tasks"] == 1
    assert result["known"]["done"]
    assert result["missing"] == {
        "task_id": "missing", "done": False, "lost": True, "error": "task not found in gateway",
    }


def test_empty_batch_is_rejected(make_task_service):
    gateway = Mock()
    result = make_task_service(gateway).pickup(crew_id="test-crew", task_ids=[])
    assert result == {"error": "task_ids must not be empty"}
    gateway.assert_not_called()


def test_timestamps_are_shared_across_task_operations_and_expire(make_task_service):
    tasks = {}

    def gateway(_crew, _crew_id, method, path, **kwargs):
        if (method, path) == ("POST", "/api/spawn"):
            task = kwargs["json"]["task"]
            tasks[task] = {"id": task, "done": False, "elapsed": 1}
            return tasks[task]
        _, _, _, task_id, *action = path.split("/")
        if method == "GET":
            return tasks[task_id]
        assert action == ["steer"]
        tasks[task_id]["result"] = kwargs["json"]["message"]
        return {}

    service = make_task_service(gateway)
    single = service.dispatch(task="single", crew_id="test-crew")
    service.dispatch(tasks=["first", "second"], crew_id="test-crew")
    assert service.steer("first", "keep going", "test-crew")["task_id"] == "first"
    picked = service.pickup(crew_id="test-crew", task_ids=["first", "single"])
    assert picked["first"]["created_at"] and picked["first"]["result"] == "keep going"
    assert picked["single"]["created_at"] == single["created_at"]

    tasks["first"]["done"] = True
    completed = service.pickup("first", "test-crew")
    assert completed["completed_at"]
    service._task_timestamps["first"]["completed_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=2)
    ).isoformat()
    service.pickup("single", "test-crew")
    assert "first" not in service._task_timestamps
    assert "single" in service._task_timestamps
