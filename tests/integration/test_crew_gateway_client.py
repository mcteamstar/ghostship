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
            return httpx.Response(403, text="stale cookie")
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
        return httpx.Response(403, text="cookie=test-cookie mc_token_5476=other-cookie")

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        client = CrewGatewayClient(
            http, refresh_cookie=lambda *_: True, restore_crew=lambda crew, _: crew, removed_crew=object()
        )
        with pytest.raises(CrewUnresponsiveError) as rejected:
            client.request_with_recovery(CREW, "contract", "GET", "/api/spawn")
    assert "HTTP 403" in str(rejected.value)
    assert "test-cookie" not in str(rejected.value)
    assert "other-cookie" not in str(rejected.value)
