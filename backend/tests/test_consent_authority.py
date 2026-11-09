import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.audit_chain import canonical_json
from app.service import ServiceError
from backend.tests.helpers import make_service


def signed_event(private, dataset_id, event_type="withdrawn"):
    payload = {
        "schema_version": "1.0",
        "event_id": str(uuid4()),
        "issuer": "https://consent.example.edu",
        "dataset_id": dataset_id,
        "source_sample_id": "SOURCE-SAMPLE-001",
        "event_type": event_type,
        "effective_at": datetime.now(UTC).isoformat(),
        "consent": {
            "use": "GRU",
            "disease": None,
            "modifiers": [],
            "population": None,
            "consent_date": "2026-10-01",
        },
    }
    signature = private.sign(canonical_json(payload).encode("ascii"))
    return {
        **payload,
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def test_signed_consent_withdrawal_is_persisted_audited_and_idempotent():
    svc = make_service()
    private = Ed25519PrivateKey.generate()
    private_bytes = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).decode()
    svc.store.x("UPDATE donors SET source_sample_id=? WHERE id=1", ("SOURCE-SAMPLE-001",))
    event = signed_event(private, svc.dataset_id)

    result = svc.apply_signed_consent_event(
        event, public_key_b64=public, trusted_issuer="https://consent.example.edu",
    )
    assert result["withdrawn"] is True
    assert svc.ds.donors[0].withdrawn is True
    stored = svc.store.one("SELECT event_type,source_record_sha256 FROM consent_events WHERE event_id=?",
                           (event["event_id"],))
    assert stored["event_type"] == "withdrawn"
    assert len(stored["source_record_sha256"]) == 64
    assert svc.audit.verify()["ok"] is True

    with pytest.raises(ServiceError, match="already applied"):
        svc.apply_signed_consent_event(
            event, public_key_b64=public, trusted_issuer="https://consent.example.edu",
        )


def test_signed_consent_rejects_tampering_and_unknown_source_sample():
    svc = make_service()
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).decode()
    event = signed_event(private, svc.dataset_id)
    event["consent"]["use"] = "HMB"

    with pytest.raises(ServiceError, match="signature"):
        svc.apply_signed_consent_event(
            event, public_key_b64=public, trusted_issuer="https://consent.example.edu",
        )

    event = signed_event(private, svc.dataset_id)
    with pytest.raises(ServiceError, match="not part"):
        svc.apply_signed_consent_event(
            event, public_key_b64=public, trusted_issuer="https://consent.example.edu",
        )


def test_signed_consent_rejects_wrong_dataset_and_untrusted_issuer():
    svc = make_service()
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )).decode()
    event = signed_event(private, "another-dataset")
    with pytest.raises(ServiceError, match="different dataset"):
        svc.apply_signed_consent_event(
            event, public_key_b64=public, trusted_issuer="https://consent.example.edu",
        )
