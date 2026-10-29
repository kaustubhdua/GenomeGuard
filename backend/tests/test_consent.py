import pytest

from app.core.consent import (
    DUO_REFERENCE,
    REASON_TEXT,
    ConsentRequest,
    DonorView,
    eligible_cohort,
    permitted,
)


def c(use="GRU", disease=None, mods=(), population=None):
    return {"use": use, "disease": disease, "modifiers": list(mods),
            "population": population, "consent_date": "2020-01-01"}


def r(purpose="general_research", **kw):
    return ConsentRequest(purpose=purpose, **kw)


# (id, consent, request, withdrawn, expected_allowed, expected_reason)
CASES = [
    # --- withdrawal always wins ---
    ("withdrawn_gru", c("GRU"), r(), True, False, "withdrawn"),
    ("withdrawn_beats_everything", c("DS", "diabetes"), r("disease_research", disease="diabetes"),
     True, False, "withdrawn"),
    # --- GRU ---
    ("gru_general", c("GRU"), r("general_research"), False, True, "ok"),
    ("gru_health", c("GRU"), r("health_research"), False, True, "ok"),
    ("gru_methods", c("GRU"), r("methods_development"), False, True, "ok"),
    ("gru_unknown_purpose", c("GRU"), r("marketing"), False, False, "purpose_unknown"),
    # --- HMB ---
    ("hmb_health", c("HMB"), r("health_research"), False, True, "ok"),
    ("hmb_biomedical", c("HMB"), r("biomedical_research"), False, True, "ok"),
    ("hmb_ancestry_blocked", c("HMB"), r("ancestry_research"), False, False, "purpose_not_health"),
    ("hmb_general_blocked", c("HMB"), r("general_research"), False, False, "purpose_not_health"),
    # --- DS ---
    ("ds_match", c("DS", "diabetes"), r("disease_research", disease="diabetes"), False, True, "ok"),
    ("ds_mismatch", c("DS", "cancer"), r("disease_research", disease="diabetes"), False, False,
     "disease_mismatch"),
    ("ds_request_has_no_disease", c("DS", "cancer"), r("health_research"), False, False,
     "disease_mismatch"),
    ("ds_malformed_no_disease", c("DS", None), r("health_research"), False, False,
     "disease_mismatch"),
    # --- commercial ---
    ("ncu_commercial", c("GRU", mods=["NCU"]), r(is_commercial=True), False, False,
     "commercial_use_blocked"),
    ("npu_commercial", c("GRU", mods=["NPU"]), r(is_commercial=True), False, False,
     "commercial_use_blocked"),
    ("ncu_noncommercial_ok", c("GRU", mods=["NCU"]), r(is_commercial=False), False, True, "ok"),
    ("commercial_without_modifier_ok", c("GRU"), r(is_commercial=True), False, True, "ok"),
    # --- methods development ---
    ("nmds_methods", c("GRU", mods=["NMDS"]), r("methods_development"), False, False,
     "methods_research_blocked"),
    ("nmds_other_purpose_ok", c("GRU", mods=["NMDS"]), r("general_research"), False, True, "ok"),
    # --- aggregate-level ---
    ("nagr_frequency", c("GRU", mods=["NAGR"]), r(data_level="frequency"), False, False,
     "aggregate_blocked"),
    ("nagr_count", c("GRU", mods=["NAGR"]), r(data_level="count"), False, False,
     "aggregate_blocked"),
    ("nagr_boolean", c("GRU", mods=["NAGR"]), r(data_level="boolean"), False, False,
     "aggregate_blocked"),
    ("nagr_record_ok", c("GRU", mods=["NAGR"]), r(data_level="record"), False, True, "ok"),
    # --- controls ---
    ("nctrl_as_control", c("GRU", mods=["NCTRL"]), r("control_cohort"), False, False,
     "controls_blocked"),
    ("nctrl_other_ok", c("GRU", mods=["NCTRL"]), r("general_research"), False, True, "ok"),
    # --- population restriction ---
    ("pop_match", c("GRU", population="POP_A"), r(population="POP_A"), False, True, "ok"),
    ("pop_mismatch", c("GRU", population="POP_A"), r(population="POP_B"), False, False,
     "population_restricted"),
    ("pop_undeclared", c("GRU", population="POP_A"), r(), False, False, "population_restricted"),
    # --- combinations and ordering ---
    ("hmb_plus_ncu_commercial_health", c("HMB", mods=["NCU"]),
     r("health_research", is_commercial=True), False, False, "commercial_use_blocked"),
    ("hmb_plus_ncu_noncommercial_health", c("HMB", mods=["NCU"]), r("health_research"),
     False, True, "ok"),
    ("ds_plus_nagr_frequency", c("DS", "cancer", mods=["NAGR"]),
     r("disease_research", disease="cancer", data_level="frequency"), False, False,
     "aggregate_blocked"),
    ("use_rule_reported_before_modifier", c("HMB", mods=["NCU"]),
     r("general_research", is_commercial=True), False, False, "purpose_not_health"),
    ("all_modifiers_clean_request", c("GRU", mods=["NCU", "NPU", "NMDS", "NAGR", "NCTRL"]),
     r("general_research", data_level="record"), False, True, "ok"),
    # --- dataset-level source terms are not participant consent ---
    ("dataset_policy_aggregate_allowed", {
        "use": "GRU", "disease": None, "modifiers": [], "population": None,
        "consent_date": None, "consent_basis": "dataset_policy",
        "source_policy_id": "public-terms-v1", "source_policy_url": "https://example.org/terms",
        "withdrawal_supported": False,
    }, r(data_level="frequency"), False, True, "ok"),
    ("dataset_policy_record_blocked", {
        "use": "GRU", "disease": None, "modifiers": [], "population": None,
        "consent_date": None, "consent_basis": "dataset_policy",
        "source_policy_id": "public-terms-v1", "source_policy_url": "https://example.org/terms",
        "withdrawal_supported": False,
    }, r(data_level="record"), False, False, "dataset_policy_individual_access_blocked"),
    ("dataset_policy_missing_source_blocked", {
        "use": "GRU", "disease": None, "modifiers": [], "population": None,
        "consent_date": None, "consent_basis": "dataset_policy",
        "source_policy_url": "https://example.org/terms", "withdrawal_supported": False,
    }, r(), False, False, "unknown_consent"),
    # --- malformed ---
    ("unknown_use_code", {"use": "XYZ", "modifiers": []}, r(), False, False, "unknown_consent"),
    ("missing_modifiers_key", {"use": "GRU"}, r(), False, True, "ok"),
]


@pytest.mark.parametrize("name,consent,request_,withdrawn,allowed,reason", CASES,
                         ids=[x[0] for x in CASES])
def test_permitted(name, consent, request_, withdrawn, allowed, reason):
    assert permitted(consent, request_, withdrawn) == (allowed, reason)


def test_at_least_25_cases_and_every_rule_covered():
    assert len(CASES) >= 25
    covered = {x[5] for x in CASES} - {"ok"}
    assert covered == set(REASON_TEXT)  # every reason code is exercised by at least one case


def test_every_reason_has_text():
    assert {x[5] for x in CASES} - {"ok"} <= set(REASON_TEXT)


def test_duo_reference_confirmed_ids_only():
    assert DUO_REFERENCE["NCU"]["id"] == "DUO:0000046"
    assert DUO_REFERENCE["NMDS"]["id"] == "DUO:0000015"
    assert all(v["id"] is None for k, v in DUO_REFERENCE.items() if k not in ("NCU", "NMDS"))


# ---------------- eligible_cohort ----------------

def donors():
    return [
        DonorView(1, "POP_A", "B1", 1, c("GRU")),
        DonorView(2, "POP_A", "B1", 1, c("HMB")),
        DonorView(3, "POP_B", "B1", 2, c("DS", "diabetes")),
        DonorView(4, "POP_B", "B2", 2, c("DS", "cancer")),
        DonorView(5, "POP_C", "B2", 3, c("GRU", mods=["NCU"])),
        DonorView(6, "POP_C", "B2", 3, c("GRU"), withdrawn=True),
    ]


def test_eligible_counts_and_reasons():
    req = r("disease_research", disease="diabetes", is_commercial=True)
    res = eligible_cohort(req, donors())
    assert res.donor_ids == [1, 2, 3]  # GRU, HMB(health purpose), DS diabetes
    assert res.considered == 6
    assert res.excluded_by_reason == {"disease_mismatch": 1, "commercial_use_blocked": 1,
                                      "withdrawn": 1}


def test_cohort_filter_applied_before_consent():
    req = r("disease_research", disease="diabetes", cohort_filter={"population": "POP_A"})
    res = eligible_cohort(req, donors())
    assert res.considered == 2  # only POP_A donors were even considered
    assert res.donor_ids == [1, 2]
    assert res.excluded_by_reason == {}


def test_cohort_filter_accepts_lists():
    req = r(cohort_filter={"cohort_id": ["B2"], "population": ["POP_B", "POP_C"]})
    assert eligible_cohort(req, donors()).considered == 3


def test_counts_only_never_contains_donor_ids():
    res = eligible_cohort(r(), donors())
    out = res.counts_only()
    assert "donor_ids" not in out and set(out) == {"eligible", "considered", "excluded_by_reason"}


def test_donor_view_has_no_genotype_field():
    assert not any("geno" in f for f in DonorView.__dataclass_fields__)


def test_empty_cohort():
    res = eligible_cohort(r(cohort_filter={"population": "NOPE"}), donors())
    assert (res.n, res.considered, res.excluded_by_reason) == (0, 0, {})


def test_synthetic_cohort_consent_records_are_all_valid():
    from app.data.synth import generate

    cohort = generate(n_donors=120, n_variants=50, n_families=24, seed=5)
    views = [DonorView(d["id"], d["population"], d["cohort_id"], d["family_id"], d["consent"],
                       d["withdrawn"]) for d in cohort.donors]
    res = eligible_cohort(r("general_research", data_level="record"), views)
    assert "unknown_consent" not in res.excluded_by_reason
    assert res.n + sum(res.excluded_by_reason.values()) == res.considered == 120
