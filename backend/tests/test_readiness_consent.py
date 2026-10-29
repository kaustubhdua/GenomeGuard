"""Regression tests for the participant-consent readiness boundary."""

from tests.helpers import make_client


def test_dataset_policy_is_not_misreported_as_participant_consent():
    svc, client = make_client()
    # Simulate a source policy that covers the dataset and a count that happens
    # to equal the sample count. This is still not participant-level evidence.
    svc.provenance = {
        "genotypes": "real_vcf",
        "consent": "source_policy",
        "consent_records_matched": 0,
        "dataset_policy_samples_scoped": svc.ds.n_donors,
    }

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503
    assert body["checks"]["participant_consent_records_verified"] is False
    assert body["ready"] is False
