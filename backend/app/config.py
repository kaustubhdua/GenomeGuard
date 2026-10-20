"""Infrastructure settings. Privacy/anomaly thresholds live in app/core/params.py (dependency-free
so the core can be tested without installing the web stack); they are re-exported here.

Override any setting with an environment variable prefixed GG_ (e.g. GG_DATABASE_URL) or .env.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.params import BANDS, CREDENTIAL_LEVELS, DATA_LEVELS, OUTCOMES, Params  # noqa: F401
from app.core.params import DEFAULT as params  # noqa: F401


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GG_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./genomeguard.db"
    allow_tamper_demo: bool = False  # enables POST /admin/tamper/{idx}; demo only
    admin_api_key: str = "dev-admin-key-change-me"
    anthropic_api_key: str | None = None  # absent -> deterministic template explanations
    llm_model: str = "claude-sonnet-5-5"
    dataset_id: str = "synthetic-cohort-1"  # one encryption key and one epsilon budget per dataset
    master_key: str = ""  # base64 32-byte key; per-dataset keys are derived from it (HKDF)

    # synthetic data defaults (section 7.1)
    seed: int = 1337
    n_donors: int = 600
    n_variants: int = 3000
    n_populations: int = 3
    n_families: int = 120
    n_planted_rare: int = 5


settings = Settings()
