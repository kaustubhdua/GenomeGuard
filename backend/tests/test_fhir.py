"""FHIR R4 Consent export of a donor's consent (pseudonymous, tagged as simulated)."""

import json
from dataclasses import replace

import pytest

from app.service import ServiceError
from tests.helpers import ADMIN, make_client, make_service


def _donor_with(svc, pred):
    return next(d for d in svc.ds.donors if not d.withdrawn and pred(d.consent))


def test_resource_has_the_required_fhir_consent_fields():
    svc = make_service()
    d = _donor_with(svc, lambda c: c["use"] == "DS")
    r = svc.donor_consent_fhir(d.id)
    assert r["resourceType"] == "Consent" and r["status"] == "active"
    assert r["scope"]["coding"][0]["code"] == "research"
    assert r["category"][0]["coding"][0]["system"] == "http://loinc.org"
    assert r["provision"]["type"] == "permit"
    assert r["policy"][0]["uri"].endswith("/docs/consent-policy.md")
    assert "not actual consent" in r["text"]["div"]
    assert r["patient"]["reference"] == f"Patient/{r['id']}"
    assert json.loads(json.dumps(r)) == r  # plain JSON, round-trips


def test_it_is_tagged_simulated_and_does_not_leak_the_donor_number():
    svc = make_service()
    d = svc.ds.donors[0]
    r = svc.donor_consent_fhir(d.id)
    tags = [t["code"] for t in r["meta"]["tag"]]
    assert "simulated-consent" in tags
    assert r["meta"]["tag"][0]["system"].endswith("/CodeSystem-genomeguard-tags.json")
    flat = json.dumps(r)
    assert f"Patient/{d.id}" not in flat and f'"id": "{d.id}"' not in flat
    assert r["id"] == svc._donor_ref(d.id) and len(r["id"]) == 12


def test_use_disease_and_modifiers_are_carried_as_duo_extensions():
    svc = make_service()
    d = _donor_with(svc, lambda c: c["use"] == "DS" and c.get("disease"))
    svc.donor_set_consent(d.id, {"use": "DS", "disease": "diabetes",
                                 "modifiers": ["NCU", "NMDS"]})
    r = svc.donor_consent_fhir(d.id)
    ext = {e["url"].rsplit("/", 1)[1].removeprefix("StructureDefinition-").removesuffix(".json"): [] for e in r["provision"]["extension"]}
    for e in r["provision"]["extension"]:
        ext[e["url"].rsplit("/", 1)[1].removeprefix("StructureDefinition-").removesuffix(".json")].append(e)
    assert ext["duo-use"][0]["valueCoding"]["code"] == "DUO:0000007"
    codes = {e["valueCoding"]["code"] for e in ext["duo-modifier"]}
    assert codes == {"DUO:0000046", "DUO:0000015"}
    assert ext["disease"][0]["valueString"] == "diabetes"


def test_standard_permission_uses_the_official_duo_identifier():
    svc = make_service()
    d = _donor_with(svc, lambda c: c["use"] == "GRU")
    use = svc.donor_consent_fhir(d.id)["provision"]["extension"][0]["valueCoding"]
    assert use["code"] == "DUO:0000042"
    assert use["system"] == "http://purl.obolibrary.org/obo/duo.owl"


def test_npoa_modifier_uses_the_official_duo_identifier():
    svc = make_service()
    d = _donor_with(svc, lambda c: c["use"] == "GRU")
    svc.donor_set_consent(d.id, {"use": "GRU", "modifiers": ["NPOA"]})
    modifier = next(
        e["valueCoding"]
        for e in svc.donor_consent_fhir(d.id)["provision"]["extension"]
        if e["url"].endswith("StructureDefinition-duo-modifier.json")
    )
    assert modifier["code"] == "DUO:0000044"
    assert modifier["system"] == "http://purl.obolibrary.org/obo/duo.owl"


def test_withdrawal_makes_the_resource_inactive():
    svc = make_service()
    d = _donor_with(svc, lambda c: True)
    assert svc.donor_consent_fhir(d.id)["status"] == "active"
    svc.donor_set_withdrawn(d.id, True)
    assert svc.donor_consent_fhir(d.id)["status"] == "inactive"


def test_endpoint_needs_the_donors_own_key_and_is_audited_without_identity():
    svc, c = make_client()
    a, b = svc.ds.donors[0], svc.ds.donors[1]
    url = f"/donor/{a.id}/consent.fhir.json"
    assert c.get(url).status_code == 401
    assert c.get(url, headers={"X-Donor-Key": svc.donor_key(b.id)}).status_code == 401
    assert c.get(url, headers=ADMIN).status_code == 401  # the steward key is not a donor key
    r = c.get(url, headers={"X-Donor-Key": svc.donor_key(a.id)})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/fhir+json")
    assert r.json()["resourceType"] == "Consent"
    last = svc.audit.entries()[-1]
    assert last["action"] == "consent.exported"
    assert last["payload"] == {"donor_ref": svc._donor_ref(a.id), "format": "fhir_r4"}
    assert last["actor"] == "donor:" + svc._donor_ref(a.id)
    assert svc.audit.verify()["ok"]


def test_dataset_policy_does_not_expose_or_mutate_fake_participant_consent():
    svc = make_service()
    donor = svc.ds.donors[0]
    policy_consent = {
        **donor.consent,
        "consent_basis": "dataset_policy",
        "consent_date": None,
        "source_policy_id": "public-terms-v1",
        "source_policy_url": "https://example.org/terms",
        "withdrawal_supported": False,
    }
    svc.ds.donors[donor.id - 1] = replace(donor, consent=policy_consent)

    with pytest.raises(ServiceError) as profile_error:
        svc.donor_profile(donor.id)
    assert profile_error.value.status == 404

    with pytest.raises(ServiceError) as consent_error:
        svc.donor_set_consent(donor.id, {"use": "GRU", "modifiers": []})
    assert consent_error.value.status == 409
    assert consent_error.value.code == "dataset_policy_not_individual_consent"

    with pytest.raises(ServiceError) as withdrawal_error:
        svc.donor_set_withdrawn(donor.id, True)
    assert withdrawal_error.value.status == 409
    assert withdrawal_error.value.code == "dataset_policy_withdrawal_unsupported"

    with pytest.raises(ServiceError) as fhir_error:
        svc.donor_consent_fhir(donor.id)
    assert fhir_error.value.status == 409
    assert fhir_error.value.code == "dataset_policy_not_individual_consent"


def test_poa_and_npuncu_are_exported_with_official_duo_identifiers():
    svc = make_service()
    d = _donor_with(svc, lambda consent: consent["use"] == "GRU")
    svc.donor_set_consent(d.id, {"use": "POA", "modifiers": ["NPUNCU"]})
    resource = svc.donor_consent_fhir(d.id)
    codings = [
        extension["valueCoding"]
        for extension in resource["provision"]["extension"]
        if "valueCoding" in extension
    ]
    assert any(
        item["code"] == "DUO:0000011"
        and item["system"] == "http://purl.obolibrary.org/obo/duo.owl"
        for item in codings
    )
    assert any(
        item["code"] == "DUO:0000018"
        and item["system"] == "http://purl.obolibrary.org/obo/duo.owl"
        for item in codings
    )
