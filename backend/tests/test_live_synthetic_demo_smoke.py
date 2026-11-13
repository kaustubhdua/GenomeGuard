from __future__ import annotations

from scripts import live_synthetic_demo_smoke as monitor


def test_get_with_retry_recovers_from_transient_cold_start(monkeypatch):
    responses = iter([
        (0, "connection closed during cold start"),
        (200, {"status": "ok"}),
    ])
    calls = []
    monkeypatch.setattr(monitor, "get", lambda *args, **kwargs: (calls.append(args[1]) or next(responses)))
    monkeypatch.setattr(monitor.time, "sleep", lambda _delay: None)
    status, payload = monitor.get_with_retry("https://example.test", "/health")
    assert status == 200
    assert payload == {"status": "ok"}
    assert calls == ["/health", "/health"]


def test_get_with_retry_does_not_retry_stable_client_errors(monkeypatch):
    calls = []
    monkeypatch.setattr(
        monitor, "get",
        lambda *args, **kwargs: (calls.append(args[1]) or (400, {"error": "bad request"})),
    )
    status, payload = monitor.get_with_retry("https://example.test", "/health")
    assert status == 400
    assert payload == {"error": "bad request"}
    assert calls == ["/health"]


def test_get_with_retry_reports_persistent_gateway_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        monitor, "get",
        lambda *args, **kwargs: (calls.append(args[1]) or (503, {"error": "unavailable"})),
    )
    monkeypatch.setattr(monitor.time, "sleep", lambda _delay: None)
    status, payload = monitor.get_with_retry("https://example.test", "/health", attempts=2)
    assert status == 503
    assert payload == {"error": "unavailable"}
    assert calls == ["/health", "/health"]
