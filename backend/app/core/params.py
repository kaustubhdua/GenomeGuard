"""Every tunable threshold in one dependency-free place (documented in docs/threat-model.md).

Override any value with an environment variable GG_<NAME_IN_CAPS>, e.g. GG_K_MIN=30.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class Params:
    # --- privacy risk (section 7.3) ---
    k_min: int = 20  # never release for cohorts smaller than this
    rare_maf: float = 0.01  # MAF below this is a "rare" variant
    min_carriers_high: int = 5  # a rare variant with 1..4 carriers -> high risk (unless hidden)
    uniqueness_medium: float = 0.01  # record level: >=1% unique -> medium
    uniqueness_high: float = 0.10  # record level: >10% unique -> high
    signal_medium: float = 1.0  # aggregate level: membership signal z >= 1 -> medium
    signal_high: float = 3.0  # aggregate level: membership signal z >= 3 -> high
    exposure_min_shared: float = 0.0078  # ignore relatives expected to share less (3rd cousin)

    # --- transformations (section 7.4) ---
    maf_floor: float = 0.01
    freq_bin_width: float = 0.05
    epsilon_budget: float = 1.0  # total per requester per dataset (simple sequential composition)
    epsilon_per_release: float = 0.5  # spent by one noised release, split across its variants
    allele_count_sensitivity: float = 2.0  # one diploid donor changes an allele count by <= 2
    max_variants_noised: int = 25  # noise scales with #variants, so cap them ("release few")

    # --- anomaly monitor (section 7.6) ---
    anomaly_window_minutes: float = 15.0
    anomaly_warn: float = 0.35
    anomaly_throttle: float = 0.55
    anomaly_freeze: float = 0.75

    @classmethod
    def from_env(cls) -> Params:
        kw = {}
        for f in fields(cls):
            raw = os.environ.get("GG_" + f.name.upper())
            if raw is not None:
                kw[f.name] = type(f.default)(raw)
        return cls(**kw)


DEFAULT = Params.from_env()

BANDS = ("low", "medium", "high")
CREDENTIAL_LEVELS = ("anonymous", "registered", "controlled")
DATA_LEVELS = ("boolean", "count", "frequency", "record")  # coarse -> fine
OUTCOMES = ("permit", "permit_with_transform", "deny", "escalate")
