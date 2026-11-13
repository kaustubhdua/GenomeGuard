"""Regression tests for bounded HTTP request parsing."""

from app.api import MAX_JSON_BODY_BYTES
from tests.helpers import make_client


def test_json_endpoints_reject_oversized_content_length_before_parsing():
    _, client = make_client()
    response = client.post(
        "/demo/session",
        content=b" " * (MAX_JSON_BODY_BYTES + 1),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "request_body_too_large"


def test_json_body_limit_does_not_change_small_json_validation():
    _, client = make_client()
    response = client.post(
        "/demo/session",
        content=b"[]",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "bad_json"


def test_json_body_limit_preserves_valid_demo_session_flow():
    _, client = make_client()
    response = client.post("/demo/session", json={"requester_id": 1})
    assert response.status_code == 200
    assert response.json()["expires_in"] == 1800
    assert response.json()["session_token"]

def test_streaming_limit_cannot_be_bypassed_without_content_length():
    import asyncio

    from starlette.requests import Request

    from app.api import _body
    from app.service import ServiceError

    chunks = [
        {"type": "http.request", "body": b" " * 700_000, "more_body": True},
        {"type": "http.request", "body": b" " * 400_000, "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    request = Request(
        {"type": "http", "method": "POST", "path": "/", "headers": []},
        receive,
    )

    async def invoke():
        try:
            await _body(request)
        except ServiceError as error:
            assert error.status == 413
            assert error.code == "request_body_too_large"
        else:
            raise AssertionError("streaming request limit was bypassed")

    asyncio.run(invoke())

def test_deeply_nested_json_is_rejected_without_uncaught_recursion_error():
    _, client = make_client()
    body = b"[" * 2_000 + b"0" + b"]" * 2_000
    response = client.post(
        "/demo/session",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "bad_json"
