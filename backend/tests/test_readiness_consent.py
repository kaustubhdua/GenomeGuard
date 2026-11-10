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


def test_policy_scope_is_never_reported_as_matched_participant_consent():
    svc, client = make_client()
    svc.provenance = {
        "genotypes": "real_vcf",
        "consent": "source_policy",
        "consent_basis": "dataset_policy",
        "consent_records_matched": svc.ds.n_donors,
        "consent_source": "policy.json",
        "consent_records_sha256": "a" * 64,
        "dataset_policy_samples_scoped": svc.ds.n_donors,
    }

    response = client.get("/health")
    body = response.json()

    assert response.status_code == 200
    assert body["participant_consent_records_matched"] == 0
    assert body["participant_consent_records_verified"] is False
    assert body["consent_provenance_consistent"] is False
    assert body["provenance"]["consent_records_matched"] == 0
    assert body["provenance"]["consent_source"] is None
    assert body["provenance"]["consent_records_sha256"] is None
    assert body["dataset_policy_samples_scoped"] == svc.ds.n_donors



def test_readiness_fails_closed_without_private_tenant_ingestion_and_operations_assurance():
    _svc, client = make_client()

    response = client.get("/health/ready")
    body = response.json()

    assert response.status_code == 503
    for gate in (
        "private_cohort_ingestion_verified",
        "tenant_processing_isolation_verified",
        "backup_retention_and_restore_verified",
        "monitoring_and_alerting_verified",
    ):
        assert body["checks"][gate] is False
    assert body["ready"] is False
