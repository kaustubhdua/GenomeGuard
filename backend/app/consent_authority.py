"""Verification of externally signed participant-consent change events."""
from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, datetime
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.audit_chain import canonical_json


class ConsentAuthorityError(ValueError):
    """A signed consent event is malformed, untrusted, or out of scope."""


_REQUIRED = {
    "schema_version", "event_id", "issuer", "dataset_id", "source_sample_id",
    "event_type", "effective_at", "consent", "signature",
}
_EVENT_TYPES = {"consent_updated", "withdrawn", "restored"}


def verify_consent_event(
    event: dict,
    *,
    public_key_b64: str,
    trusted_issuer: str,
    expected_dataset_id: str,
) -> tuple[dict, str]:
    """Verify a detached Ed25519 signature over the complete event excluding signature."""
    if not isinstance(event, dict) or set(event) != _REQUIRED:
        raise ConsentAuthorityError("consent event has missing or unexpected fields")
    if event.get("schema_version") != "1.0":
        raise ConsentAuthorityError("unsupported consent event schema version")
    if event.get("issuer") != trusted_issuer or not trusted_issuer:
        raise ConsentAuthorityError("consent event issuer is not trusted")
    if event.get("dataset_id") != expected_dataset_id:
        raise ConsentAuthorityError("consent event belongs to a different dataset")
    if not isinstance(event.get("source_sample_id"), str) or not (
        1 <= len(event["source_sample_id"]) <= 200
    ):
        raise ConsentAuthorityError("source sample identifier is missing or invalid")
    if event.get("event_type") not in _EVENT_TYPES:
        raise ConsentAuthorityError("unsupported consent event type")
    if not isinstance(event.get("consent"), dict):
        raise ConsentAuthorityError("consent must be an object")
    try:
        UUID(event["event_id"])
        effective = event["effective_at"]
        if not isinstance(effective, str):
            raise ValueError
        effective_at = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        if effective_at.tzinfo is None or effective_at.utcoffset() is None:
            raise ValueError("effective_at must include an explicit timezone")
        if effective_at > datetime.now(UTC):
            raise ValueError("future-effective consent events must not be applied immediately")
        public_bytes = base64.b64decode(public_key_b64, validate=True)
        if len(public_bytes) != 32:
            raise ValueError
        signature_text = event["signature"]
        if not isinstance(signature_text, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{86}", signature_text
        ):
            raise ValueError
        signature = base64.urlsafe_b64decode(signature_text + "==")
        payload = {key: value for key, value in event.items() if key != "signature"}
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(
            signature, canonical_json(payload).encode("ascii")
        )
    except (ValueError, TypeError, KeyError, InvalidSignature) as exc:
        raise ConsentAuthorityError("consent event signature or required fields are invalid") from exc
    digest = hashlib.sha256(canonical_json(payload).encode("ascii")).hexdigest()
    return payload, digest
