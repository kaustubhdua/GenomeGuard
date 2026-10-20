"""Infrastructure settings, read from environment variables prefixed GG_ (e.g. GG_DB_PATH).
Privacy / anomaly thresholds live in app/core/params.py (also overridable via GG_<NAME>)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.core.params import BANDS, CREDENTIAL_LEVELS, DATA_LEVELS, OUTCOMES, Params  # noqa: F401
from app.core.params import DEFAULT as params  # noqa: F401


def _env(name: str, default, cast=str):
    raw = os.environ.get("GG_" + name.upper())
    if raw is None:
        return default
    if cast is bool:
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return cast(raw)


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: _env("db_path", "./genomeguard.sqlite3"))
    allow_tamper_demo: bool = field(default_factory=lambda: _env("allow_tamper_demo", False, bool))
    demo_mode: bool = field(default_factory=lambda: _env("demo_mode", True, bool))
    admin_api_key: str = field(default_factory=lambda: _env("admin_api_key", "demo-admin-key"))
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY") or _env("anthropic_api_key", None))
    llm_model: str = field(default_factory=lambda: _env("llm_model", "claude-sonnet-5-5"))
    master_key: str = field(default_factory=lambda: _env("master_key", ""))
    dataset_id: str = field(default_factory=lambda: _env("dataset_id", "synthetic-cohort-1"))
    seed: int = field(default_factory=lambda: _env("seed", 1337, int))
    n_donors: int = field(default_factory=lambda: _env("n_donors", 600, int))
    n_variants: int = field(default_factory=lambda: _env("n_variants", 3000, int))
    n_populations: int = field(default_factory=lambda: _env("n_populations", 3, int))
    n_families: int = field(default_factory=lambda: _env("n_families", 120, int))
    n_planted_rare: int = field(default_factory=lambda: _env("n_planted_rare", 5, int))


def get_settings() -> Settings:
    return Settings()


settings = Settings()
