"""Offline-only agent runtime.

GenomeGuard deliberately makes no outbound AI-provider requests. Agent explanations use
reviewable deterministic templates and the steward copilot uses its bounded rules planner.
The constructor retains legacy arguments for source compatibility, but ignores credentials,
provider names and transports. No network transport is implemented here.
"""
from __future__ import annotations


class LLM:
    """Compatibility facade for the former hosted-LLM client; always unavailable."""

    def __init__(self, api_key=None, model="offline-deterministic", transport=None,
                 timeout=0.0, provider="offline") -> None:
        self.api_key = None
        self.model = "template"
        self.provider = "offline"
        self.timeout = 0.0
        self.transport = None

    @property
    def available(self) -> bool:
        return False

    def complete(self, system: str, user: str, max_tokens: int = 400) -> None:
        """Never contacts a remote provider; callers use deterministic local templates."""
        return None
