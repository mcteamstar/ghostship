"""Exercise the gateway client with the installed HTTP library."""

import json
import threading
from concurrent.futures import Future

import httpx2 as httpx
import pytest

from transport import lifecycle
from transport.crew_gateway import CrewGatewayClient, CrewUnresponsiveError


CREW = {"container": "gs-contract", "cookie": "test-cookie", "acp_backend": "codex"}


def test_gateway_wire_contract():
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"id": "accepted"})

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(http, refresh_cookie=None, restore_crew=None, removed_crew=object())
        result = client.request_with_recovery(CREW, "contract", "POST", "/api/spawn", json={"task": "hello"})
        with pytest.raises(ValueError, match="X-Internal-Secret"):
            client.request(CREW, "GET", "/api/spawn", headers={"X-Internal-Secret": "blocked"})

    assert result == {"id": "accepted"}
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "http://gs-contract:5476/api/spawn"
    assert request.headers["origin"] == "http://gs-contract:5476"
    assert request.headers["cookie"] == "mc_token_5476=test-cookie"
    assert json.loads(request.content) == {"task": "hello", "backend": "codex"}


def test_gateway_restoration_can_make_one_shot_request(monkeypatch):
    seen = []

    def handle(request):
        seen.append(request.url.path)
        if seen == ["/api/spawn/worker"]:
            return httpx.Response(403, headers={"X-Auth-Required": "true"},
                                  json={"code": "forbidden", "error": "token expired"})
        return httpx.Response(200, json={"done": True})

    def restore(crew, crew_id):
        assert client.recovery_lock(crew_id).locked()
        assert lifecycle._crew_api(crew, "GET", "/api/ready") == {"done": True}
        return crew

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(
            http, refresh_cookie=lambda *_: False, restore_crew=restore, removed_crew=object()
        )
        monkeypatch.setattr(lifecycle, "_gateway_client", client)
        assert lifecycle._get_recovery_lock("contract") is client.recovery_lock("contract")
        result = Future()

        def request():
            try:
                result.set_result(
                    lifecycle._crew_api_with_recovery(CREW, "contract", "GET", "/api/spawn/worker")
                )
            except BaseException as exc:
                result.set_exception(exc)

        threading.Thread(target=request, daemon=True).start()
        assert result.result(timeout=2) == {"done": True}
    assert seen == ["/api/spawn/worker", "/api/ready", "/api/spawn/worker"]


def test_recovery_error_redacts_real_http_response():
    def handle(_request):
        return httpx.Response(502, text="cookie=test-cookie mc_token_5476=other-cookie")

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(
            http, refresh_cookie=lambda *_: True, restore_crew=lambda crew, _: crew, removed_crew=object()
        )
        with pytest.raises(CrewUnresponsiveError) as rejected:
            client.request_with_recovery(CREW, "contract", "POST", "/api/spawn", json={"task": "hello"})
    assert "HTTP 502" in str(rejected.value)
    assert "test-cookie" not in str(rejected.value)
    assert "other-cookie" not in str(rejected.value)


@pytest.mark.parametrize("path", ["/api/spawn", "/api/spawn/prior/continue", "/api/spawn/prior/steer", "/api/crons"])
@pytest.mark.parametrize("failure", ["disconnect", "server-error", "misleading-memory-error", "bad-json"])
def test_ambiguous_write_is_never_replayed(path, failure):
    from transport.crew_gateway import GatewayAcceptanceUnknown

    submitted = []

    def handle(request):
        submitted.append(request)
        if failure == "disconnect":
            raise httpx.ReadError("response lost", request=request)
        if failure == "server-error":
            return httpx.Response(503, text="temporarily unavailable")
        if failure == "misleading-memory-error":
            return httpx.Response(503, text="upstream response lost during memory pressure")
        return httpx.Response(200, text="malformed")

    def unexpected_recovery(*_):
        pytest.fail("ambiguous write must never trigger write replay or crew recovery")

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(
            http, refresh_cookie=unexpected_recovery, restore_crew=unexpected_recovery,
            removed_crew=object(),
        )
        with pytest.raises(GatewayAcceptanceUnknown):
            client.request_with_recovery(CREW, "contract", "POST", path, json={"task": "one"})
    assert len(submitted) == 1


@pytest.mark.parametrize("headers,body,retry", [
    ({"X-Auth-Required": "true"}, {"code": "forbidden", "error": "token expired"}, True),
    ({}, {"code": "forbidden", "error": "token expired"}, False),
    ({"X-Auth-Required": "true"}, {"code": "forbidden", "error": "origin mismatch"}, False),
])
def test_write_retries_only_after_explicit_refreshable_auth_refusal(headers, body, retry):
    calls = []
    refreshes = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(403, headers=headers, json=body)
        return httpx.Response(200, json={"id": "accepted"})

    def refresh(crew, _crew_id):
        refreshes.append(True)
        crew["cookie"] = "fresh-cookie"
        return True

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(http, refresh_cookie=refresh, restore_crew=None, removed_crew=object())
        if retry:
            assert client.request_with_recovery(
                dict(CREW), "contract", "POST", "/api/spawn", json={"task": "one"}
            ) == {"id": "accepted"}
            assert calls[1].headers["cookie"] == "mc_token_5476=fresh-cookie"
        else:
            with pytest.raises(httpx.HTTPStatusError):
                client.request_with_recovery(CREW, "contract", "POST", "/api/spawn", json={"task": "one"})
    assert len(calls) == 1 + retry
    assert len(refreshes) == retry


def test_explicit_unsupported_steer_remains_available_to_follow_up_adapter():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        502, json={"code": "steer_failed", "error": "steer_unsupported: queue a follow-up"},
    ))) as http:
        client = CrewGatewayClient(http, refresh_cookie=None, restore_crew=None, removed_crew=object())
        with pytest.raises(httpx.HTTPStatusError) as rejected:
            client.request_with_recovery(
                CREW, "contract", "POST", "/api/spawn/task/steer", json={"message": "one"}
            )
    assert rejected.value.response.status_code == 502
