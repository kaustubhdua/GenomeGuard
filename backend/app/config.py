"""Central configuration. Every threshold used by the risk/anomaly logic lives here so it can be
documented in docs/threat-model.md and changed in one place.

Override any value with an environment variable prefixed GG_ (e.g. GG_K_MIN=30) or a .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GG_", env_file=".env", extra="ignore")

    # --- infrastructure ---
    database_url: str = "sqlite:///./genomeguard.db"
    genotype_dir: str = "./data_store"  # compressed numpy genotype files; never served by the API
    allow_tamper_demo: bool = False  # enables POST /admin/tamper/{idx}; demo only
    admin_api_key: str = "dev-admin-key-change-me"
    anthropic_api_key: str | None = None  # absent -> deterministic template explanations

    # --- synthetic data defaults (section 7.1) ---
    seed: int = 1337
    n_donors: int = 600
    n_variants: int = 3000
    n_populations: int = 3
    n_families: int = 120
    rare_maf: float = 0.01  # MAF below this counts as "rare"
    n_planted_rare: int = 5  # very rare variants (MAF ~0.003) used in the demo

    # --- privacy risk (section 7.3) ---
    k_min: int = 20  # never release for cohorts smaller than this
    uniqueness_medium: float = 0.01  # >= 1% unique -> medium
    uniqueness_high: float = 0.10  # > 10% unique -> high
    min_carriers_high: int = 5  # a rare variant with fewer carriers -> high risk
    max_relative_meioses: int = 8  # up to third cousins (4+4 meioses); farther pairs are ignored
    exposure_min_shared: float = 0.0078  # ignore pairs expected to share less than this

    # --- transformations (section 7.4) ---
    maf_floor: float = 0.01
    freq_bin_width: float = 0.05
    epsilon_budget: float = 1.0  # total per requester per dataset (simple sequential composition)
    allele_count_sensitivity: float = 2.0  # diploid allele count

    # --- anomaly monitor (section 7.6) ---
    anomaly_window_minutes: int = 15
    anomaly_warn: float = 0.4
    anomaly_throttle: float = 0.6
    anomaly_freeze: float = 0.8


settings = Settings()

RISK_BANDS = ("low", "medium", "high")
CREDENTIAL_LEVELS = ("anonymous", "registered", "controlled")
DATA_LEVELS = ("boolean", "count", "frequency", "record")  # coarse -> fine
OUTCOMES = ("permit", "permit_with_transform", "deny", "escalate")
