import asyncio

import httpx
import pytest

from orchestration import upstream
from orchestration.errors import (
    FlowError,
    UpstreamTimeout,
    UpstreamUnreachable,
    flow_error_from,
    is_contract_error,
    translate_error,
)

BASE = "http://svc:1"


def run(coro):
    return asyncio.run(coro)


def make_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_call_builds_internal_url_headers_and_user_id():
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"ok": True})

    async def go():
        async with make_client(handler) as c:
            return await upstream.call(
                c, BASE, "logic", "POST", "/games", user_id="u1",
                params={"a": "1"}, json={"x": 1}, headers={"Idempotency-Key": "k"},
                timeout=5,
            )

    r = run(go())
    req = seen[0]
    assert r.status_code == 200
    assert str(req.url) == f"{BASE}/internal/logic/games?a=1"
    assert req.method == "POST"
    assert req.headers["x-user-id"] == "u1"
    assert req.headers["idempotency-key"] == "k"
    assert req.headers["accept"] == "application/json"


def test_call_without_user_id_sends_no_header():
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(204)

    async def go():
        async with make_client(handler) as c:
            await upstream.call(c, BASE, "profile", "DELETE", "/users/1", timeout=5)

    run(go())
    assert "x-user-id" not in seen[0].headers


@pytest.mark.parametrize(
    "exc, expected",
    [
        (httpx.ReadTimeout("t"), UpstreamTimeout),
        (httpx.ConnectError("c"), UpstreamUnreachable),
    ],
)
def test_call_translates_transport_failures(exc, expected):
    def handler(req):
        raise exc

    async def go():
        async with make_client(handler) as c:
            await upstream.call(c, BASE, "logic", "GET", "/games/1", timeout=5)

    with pytest.raises(expected) as e:
        run(go())
    assert e.value.status == 503 and e.value.code == "SERVICES_UNAVAILABLE"


def test_call_returns_upstream_errors_untranslated():
    def handler(req):
        return httpx.Response(409, json={"error": {"code": "VERSION_CONFLICT", "message": "m"}})

    async def go():
        async with make_client(handler) as c:
            return await upstream.call(c, BASE, "logic", "POST", "/games/1/moves", timeout=5)

    assert run(go()).status_code == 409


def test_contract_error_passes_through_unchanged():
    resp = httpx.Response(409, json={"error": {"code": "NOT_YOUR_TURN", "message": "no"}})
    err = flow_error_from(resp, service="logic")
    assert isinstance(err, FlowError)
    assert (err.status, err.code, err.message) == (409, "NOT_YOUR_TURN", "no")


@pytest.mark.parametrize(
    "status, service, kwargs, expected",
    [
        (400, "logic", {}, (400, "VALIDATION_ERROR")),
        (401, "auth", {"unauthorized_code": "INVALID_CREDENTIALS"}, (401, "INVALID_CREDENTIALS")),
        (404, "logic", {}, (404, "GAME_NOT_FOUND")),
        (404, "multiplayer", {}, (404, "MATCH_NOT_FOUND")),
        (404, "unknown", {}, (404, "NOT_FOUND")),
        (409, "auth", {"conflict_code": "USERNAME_TAKEN"}, (409, "USERNAME_TAKEN")),
        (409, "auth", {}, (502, "UPSTREAM_ERROR")),
        (503, "logic", {}, (503, "SERVICES_UNAVAILABLE")),
        (504, "logic", {}, (503, "SERVICES_UNAVAILABLE")),
        (500, "logic", {}, (502, "UPSTREAM_ERROR")),
    ],
)
def test_translate_error_table(status, service, kwargs, expected):
    out_status, code, _ = translate_error(status, service=service, **kwargs)
    assert (out_status, code) == expected


def test_non_contract_error_is_translated():
    resp = httpx.Response(404, text="not json")
    err = flow_error_from(resp, service="tutor")
    assert (err.status, err.code) == (404, "ANALYSIS_NOT_FOUND")


def test_is_contract_error_requires_code_and_message():
    assert is_contract_error({"error": {"code": "X", "message": "m"}})
    assert not is_contract_error({"error": {"code": "X"}})
    assert not is_contract_error({"error": "x"})
    assert not is_contract_error(None)
