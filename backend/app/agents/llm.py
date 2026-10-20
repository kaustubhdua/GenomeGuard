"""Tiny LLM client over plain HTTPS (no SDK to install) with a deterministic fallback.

`complete()` returns None when there is no API key or the call fails; callers then use the
template text, so the demo never depends on the network. A `transport` can be injected for tests.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

API_URL = "https://api.anthropic.com/v1/messages"


def _default_transport(url: str, headers: dict, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URL)
        return json.loads(resp.read())


class LLM:
    def __init__(self, api_key: str | None, model: str, transport: Callable | None = None,
                 timeout: float = 20.0) -> None:
        self.api_key, self.model, self.timeout = api_key, model, timeout
        self.transport = transport or _default_transport

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, max_tokens: int = 400) -> str | None:
        if not self.available:
            return None
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": user}]}
        try:
            data = self.transport(API_URL, headers, body, self.timeout)
            text = "".join(b.get("text", "") for b in data.get("content", [])
                           if b.get("type") == "text").strip()
            return text or None
        except Exception:  # network, auth, quota...: fall back to the template
            return None
