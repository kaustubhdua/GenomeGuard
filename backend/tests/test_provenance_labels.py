from app.service import _encryption_provenance


def test_synthetic_provenance_does_not_claim_public_cohort_is_embedded():
    label = _encryption_provenance("synthetic")
    assert "synthetic-only cohort" in label
    assert "no real participant genotypes" in label
    assert "public cohort artifact is plaintext" not in label


def test_real_vcf_provenance_discloses_plaintext_public_image_artifact():
    label = _encryption_provenance("real_vcf")
    assert "public cohort artifact is plaintext" in label
    assert "Private or controlled-access data are not supported" in label


def test_unknown_or_custom_provenance_fails_closed():
    label = _encryption_provenance("custom")
    assert "source provenance are not established" in label
    assert "Do not use for private or controlled-access data" in label
