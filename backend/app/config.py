"""Infrastructure settings, read from environment variables prefixed GG_."""
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
    # PostgreSQL is selected when GG_DATABASE_URL is set; SQLite remains for local demo/testing.
    database_url: str = field(default_factory=lambda: _env("database_url", ""))
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
    # Non-demo mode requires real genotypes and source-matched authorization records.
    real_cohort_file: str = field(default_factory=lambda: _env("real_cohort_file", ""))


def get_settings() -> Settings:
    return Settings()


settings = Settings()


def validate_settings(s: Settings) -> None:
    """Fail closed for non-demo deployments with unsafe security settings."""
    if s.demo_mode:
        return

    problems: list[str] = []
    if s.admin_api_key == "demo-admin-key" or len(s.admin_api_key.strip()) < 32:
        problems.append("GG_ADMIN_API_KEY must be a unique secret of at least 32 characters")
    if s.allow_tamper_demo:
        problems.append("GG_ALLOW_TAMPER_DEMO must be false")
    if not (s.real_cohort_file or "").strip():
        problems.append("GG_REAL_COHORT_FILE must point to a real cohort with explicit consent records")
    if s.dataset_id == "synthetic-cohort-1" or not s.dataset_id.strip():
        problems.append("GG_DATASET_ID must be a unique identifier for the approved real cohort")
    if not s.master_key:
        problems.append("GG_MASTER_KEY must be set to a random base64-encoded 32-byte key")
    else:
        import base64
        try:
            key = base64.b64decode(s.master_key, validate=True)
        except (ValueError, base64.binascii.Error):
            key = b""
        if len(key) != 32:
            problems.append("GG_MASTER_KEY must decode to exactly 32 bytes")
    if problems:
        raise ValueError("Unsafe non-demo configuration: " + "; ".join(problems))
