"""Regression tests for bounded HTTP request parsing."""

from tests.helpers import make_client

from app.api import MAX_JSON_BODY_BYTES


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
