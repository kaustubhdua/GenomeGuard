from scripts import staging_smoke


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200, content_type: str = "application/json"):
        self.body = body
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int):
        return self.body[:limit]


def test_get_json_returns_status_and_object_payload(monkeypatch):
    monkeypatch.setattr(
        staging_smoke, "urlopen",
        lambda request, timeout: FakeResponse(b'{"status":"ok"}', status=200),
    )

    assert staging_smoke.get_json("https://example.test", "/health", 5) == (
        200, {"status": "ok"},
    )


def test_get_json_identifies_non_json_endpoint_without_echoing_body(monkeypatch):
    monkeypatch.setattr(
        staging_smoke, "urlopen",
        lambda request, timeout: FakeResponse(
            b"<html>proxy error with secret-like content</html>",
            status=502,
            content_type="text/html; charset=utf-8",
        ),
    )

    try:
        staging_smoke.get_json("https://example.test", "/demo/requesters", 5)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("non-JSON response must fail the smoke check")

    assert "/demo/requesters" in message
    assert "HTTP 502" in message
    assert "text/html" in message
    assert "secret-like content" not in message


def test_get_json_rejects_non_object_json(monkeypatch):
    monkeypatch.setattr(
        staging_smoke, "urlopen",
        lambda request, timeout: FakeResponse(b'["unexpected"]'),
    )

    try:
        staging_smoke.get_json("https://example.test", "/health", 5)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("non-object JSON must fail the smoke check")

    assert "/health" in message
    assert "non-object JSON" in message
