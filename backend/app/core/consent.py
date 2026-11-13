"""DUO-inspired consent policy engine (section 7.2).

Pure Python: no database or web imports, so every rule is unit-testable in isolation.

Each donor carries a consent record built from GA4GH Data Use Ontology (DUO) style codes:

    {"use": "GRU" | "HMB" | "DS" | "POA", "disease": "diabetes" | None,
     "modifiers": ["NCU", "NPU", "NPUNCU", "NMDS", "NPOA", "NAGR", "NCTRL"], "population": None | "POP_A",
     "consent_date": "YYYY-MM-DD"}

`permitted(consent, request, withdrawn)` returns (allowed, reason_code). The FIRST failing rule
wins, in a fixed order, so the reason in an explanation is deterministic:

    1 withdrawn            donor withdrew: always excluded (DPDP/GDPR: withdrawal must work)
    2 purpose_unknown      the request's purpose is not a recognised research purpose
    3 use rule             GRU: any research | HMB: health/biomedical purposes only |
                           DS: request.disease must equal consent.disease |
                           POA: population-origins/ancestry research only
    4 modifiers            NCU/NPUNCU require verified non-commercial use; NPU/NPUNCU require
                           verified not-for-profit organisation status; NMDS blocks methods
                           development; NPOA blocks ancestry research; NAGR blocks aggregate
                           data levels; NCTRL blocks use as controls
    5 population           a population-restricted consent only allows requests that declare
                           that same population

Not modelled (be honest about it): the DUO consent-form-date limit and RS-POP free-text variants.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

# Official DUO identifiers are recorded only for terms confirmed against the
# GA4GH/EBI vocabulary. NAGR and NCTRL are GenomeGuard policy extensions, not DUO.
DUO_REFERENCE: dict[str, dict[str, str | None]] = {
    "GRU": {"id": "DUO:0000042", "meaning": "General research use"},
    "HMB": {"id": "DUO:0000006", "meaning": "Health or medical or biomedical research"},
    "DS": {"id": "DUO:0000007", "meaning": "Disease-specific research"},
    "POA": {"id": "DUO:0000011", "meaning": "Population origins or ancestry research only"},
    "NPU": {"id": "DUO:0000045", "meaning": "Not-for-profit organisation use only"},
    "NPUNCU": {"id": "DUO:0000018", "meaning": "Not-for-profit and non-commercial use only"},
    "NCU": {"id": "DUO:0000046", "meaning": "Non-commercial use only"},
    "NMDS": {"id": "DUO:0000015", "meaning": "No general methods research"},
    "NPOA": {"id": "DUO:0000044", "meaning": "Population origins or ancestry research prohibited"},
    "NAGR": {
        "id": None,
        "meaning": "No aggregate-level general research (spec rule)",
    },
    "NCTRL": {
        "id": None,
        "meaning": "No use as a control set",
    },
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
    "commercial_use_blocked": "consent forbids commercial use (NCU/NPUNCU)",
    "commercial_use_unverified": "commercial-use status has not been independently verified for NCU/NPUNCU",
    "nonprofit_status_unverified": "requesting organisation not-for-profit status has not been verified for NPU/NPUNCU",
    "nonprofit_use_blocked": "consent is limited to not-for-profit organisations (NPU/NPUNCU)",
    "purpose_not_population_origins": "consent permits only population origins or ancestry research (POA)",
    "methods_research_blocked": "consent forbids methods-development research (NMDS)",
    "population_origins_blocked": "consent forbids population origins or ancestry research (NPOA)",
    "aggregate_blocked": "consent forbids aggregate-level research use (NAGR)",
    "controls_blocked": "consent forbids use as a control set (NCTRL)",
    "population_restricted": "consent is restricted to a different population",
    "unknown_consent": "consent record is malformed",
    "synthetic_consent_not_authorized": "synthetic demo consent cannot authorize research-mode data access",
    "dataset_policy_individual_access_blocked": "dataset-level terms do not authorize individual-level record access",
}


@dataclass(frozen=True)
class ConsentRequest:
    """The parts of a data request that consent cares about."""

    purpose: str
    disease: str | None = None
    is_commercial: bool | None = None
    data_level: str = "frequency"  # boolean | count | frequency | record
    population: str | None = None  # population the study declares it is about, if any
    cohort_filter: dict = field(default_factory=dict)
    organization_is_nonprofit: bool | None = None
    demo_mode: bool = False


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

    # Dataset-level public-release terms are not participant consent. They may support
    # aggregate research under documented source terms, but never individual-level output.
    basis = consent.get("consent_basis")
    if basis == "synthetic_demo":
        if not request.demo_mode:
            return False, "synthetic_consent_not_authorized"
    elif basis == "dataset_policy":
        if (consent.get("consent_date") is not None
                or not isinstance(consent.get("source_policy_id"), str)
                or not consent.get("source_policy_id", "").strip()
                or not isinstance(consent.get("source_policy_url"), str)
                or not consent.get("source_policy_url", "").startswith("https://")
                or consent.get("withdrawal_supported") is not False):
            return False, "unknown_consent"
        if request.data_level == "record":
            return False, "dataset_policy_individual_access_blocked"
    elif basis != "participant_record":
        return False, "unknown_consent"

    use = consent.get("use")
    if use not in ("GRU", "HMB", "DS", "POA"):
        return False, "unknown_consent"
    if request.purpose not in RESEARCH_PURPOSES:
        return False, "purpose_unknown"

    if use == "HMB" and request.purpose not in HEALTH_PURPOSES:
        return False, "purpose_not_health"
    if use == "DS" and (request.disease is None or request.disease != consent.get("disease")):
        return False, "disease_mismatch"
    if use == "POA" and request.purpose not in {"population_genetics", "ancestry_research"}:
        return False, "purpose_not_population_origins"

    mods = set(consent.get("modifiers") or [])
    if mods & {"NCU", "NPUNCU"}:
        if request.is_commercial is None:
            return False, "commercial_use_unverified"
        if request.is_commercial:
            return False, "commercial_use_blocked"
    if mods & {"NPU", "NPUNCU"}:
        if request.organization_is_nonprofit is None:
            return False, "nonprofit_status_unverified"
        if not request.organization_is_nonprofit:
            return False, "nonprofit_use_blocked"
    if "NMDS" in mods and request.purpose in METHODS_PURPOSES:
        return False, "methods_research_blocked"
    if "NPOA" in mods and request.purpose in {"population_genetics", "ancestry_research"}:
        return False, "population_origins_blocked"
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
