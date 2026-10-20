"""DUO-inspired consent policy engine (section 7.2).

Pure Python: no database or web imports, so every rule is unit-testable in isolation.

Each donor carries a consent record built from GA4GH Data Use Ontology (DUO) style codes:

    {"use": "GRU" | "HMB" | "DS", "disease": "diabetes" | None,
     "modifiers": ["NCU", "NPU", "NMDS", "NAGR", "NCTRL"], "population": None | "POP_A",
     "consent_date": "YYYY-MM-DD"}

`permitted(consent, request, withdrawn)` returns (allowed, reason_code). The FIRST failing rule
wins, in a fixed order, so the reason in an explanation is deterministic:

    1 withdrawn            donor withdrew: always excluded (DPDP/GDPR: withdrawal must work)
    2 purpose_unknown      the request's purpose is not a recognised research purpose
    3 use rule             GRU: any research | HMB: health/biomedical purposes only |
                           DS: request.disease must equal consent.disease
    4 modifiers            NCU/NPU block commercial use; NMDS blocks methods development;
                           NAGR blocks aggregate-level data levels; NCTRL blocks use as controls
    5 population           a population-restricted consent only allows requests that declare
                           that same population

Not modelled (be honest about it): the DUO consent-form-date limit and RS-POP free-text variants.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

# DUO terms. Only the IDs confirmed from the official ontology are filled in; for any other ID,
# look it up in the official duo.owl rather than guessing (see `make fetch-real`).
DUO_REFERENCE: dict[str, dict[str, str | None]] = {
    "GRU": {"id": None, "meaning": "General research use"},
    "HMB": {"id": None, "meaning": "Health / medical / biomedical research only"},
    "DS": {"id": None, "meaning": "Disease-specific research (named disease only)"},
    "NPU": {"id": None, "meaning": "Not-for-profit use only"},
    "NCU": {"id": "DUO:0000046", "meaning": "No commercial use"},
    "NMDS": {"id": "DUO:0000015", "meaning": "No methods development research"},
    "NAGR": {"id": None, "meaning": "No aggregate-level general research (spec rule)"},
    "NCTRL": {"id": None, "meaning": "No use as a control set"},
}

# Request purposes. "Health" purposes satisfy HMB; every purpose here counts as research.
HEALTH_PURPOSES = frozenset({"health_research", "medical_research", "biomedical_research",
                             "disease_research", "clinical_research"})
OTHER_RESEARCH_PURPOSES = frozenset({"general_research", "population_genetics", "ancestry_research",
                                     "methods_development", "control_cohort", "education"})
RESEARCH_PURPOSES = HEALTH_PURPOSES | OTHER_RESEARCH_PURPOSES
METHODS_PURPOSES = frozenset({"methods_development"})
CONTROL_PURPOSES = frozenset({"control_cohort"})
AGGREGATE_LEVELS = frozenset({"boolean", "count", "frequency"})  # "record" is individual-level

REASON_TEXT = {
    "withdrawn": "donor withdrew consent",
    "purpose_unknown": "request purpose is not a recognised research purpose",
    "purpose_not_health": "consent covers health/biomedical research only (HMB)",
    "disease_mismatch": "consent is limited to a different disease area (DS)",
    "commercial_use_blocked": "consent forbids commercial / for-profit use (NCU/NPU)",
    "methods_research_blocked": "consent forbids methods-development research (NMDS)",
    "aggregate_blocked": "consent forbids aggregate-level research use (NAGR)",
    "controls_blocked": "consent forbids use as a control set (NCTRL)",
    "population_restricted": "consent is restricted to a different population",
    "unknown_consent": "consent record is malformed",
}


@dataclass(frozen=True)
class ConsentRequest:
    """The parts of a data request that consent cares about."""

    purpose: str
    disease: str | None = None
    is_commercial: bool = False
    data_level: str = "frequency"  # boolean | count | frequency | record
    population: str | None = None  # population the study declares it is about, if any
    cohort_filter: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DonorView:
    """Everything the engine may see about a donor. Deliberately has NO genotype field."""

    id: int
    population: str
    cohort_id: str
    family_id: int
    consent: dict
    withdrawn: bool = False


@dataclass
class EligibleCohort:
    donor_ids: list[int]  # internal use only: API layers must never return these
    considered: int  # donors matching the cohort filter, before consent
    excluded_by_reason: dict[str, int]

    @property
    def n(self) -> int:
        return len(self.donor_ids)

    def counts_only(self) -> dict:
        """Safe-to-return summary: numbers and reason codes, never donor identities."""
        return {"eligible": self.n, "considered": self.considered,
                "excluded_by_reason": dict(self.excluded_by_reason)}


def permitted(consent: dict, request: ConsentRequest, withdrawn: bool = False) -> tuple[bool, str]:
    """Is this donor's consent compatible with the request? Returns (allowed, reason_code);
    reason_code is "ok" when allowed."""
    if withdrawn:
        return False, "withdrawn"
    use = consent.get("use")
    if use not in ("GRU", "HMB", "DS"):
        return False, "unknown_consent"
    if request.purpose not in RESEARCH_PURPOSES:
        return False, "purpose_unknown"

    if use == "HMB" and request.purpose not in HEALTH_PURPOSES:
        return False, "purpose_not_health"
    if use == "DS" and (request.disease is None or request.disease != consent.get("disease")):
        return False, "disease_mismatch"

    mods = set(consent.get("modifiers") or [])
    if mods & {"NCU", "NPU"} and request.is_commercial:
        return False, "commercial_use_blocked"
    if "NMDS" in mods and request.purpose in METHODS_PURPOSES:
        return False, "methods_research_blocked"
    if "NAGR" in mods and request.data_level in AGGREGATE_LEVELS:
        return False, "aggregate_blocked"
    if "NCTRL" in mods and request.purpose in CONTROL_PURPOSES:
        return False, "controls_blocked"

    restricted_to = consent.get("population")
    if restricted_to and request.population != restricted_to:
        return False, "population_restricted"
    return True, "ok"


def _matches_filter(donor: DonorView, flt: dict) -> bool:
    """Cohort filter: each key accepts a single value or a list. Supported keys: cohort_id,
    population. Unknown keys are ignored here (the risk module may use more)."""
    for key in ("cohort_id", "population"):
        want = flt.get(key)
        if want is None:
            continue
        allowed = want if isinstance(want, (list, tuple, set)) else [want]
        if getattr(donor, key) not in allowed:
            return False
    return True


def eligible_cohort(request: ConsentRequest, donors: Iterable[DonorView]) -> EligibleCohort:
    """Apply the cohort filter FIRST, then consent. Counts exclusions per reason so the
    explanation can say how many donors were excluded and why."""
    ids: list[int] = []
    reasons: Counter[str] = Counter()
    considered = 0
    for d in donors:
        if not _matches_filter(d, request.cohort_filter):
            continue
        considered += 1
        ok, reason = permitted(d.consent, request, d.withdrawn)
        if ok:
            ids.append(d.id)
        else:
            reasons[reason] += 1
    return EligibleCohort(ids, considered, dict(reasons))
